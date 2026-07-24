import geopandas as gpd
import duckdb
from src import config


def run_stage_analysis(export_intermediates: bool = None):
    """
    Stage 3: Executes spatial multi-criteria analysis (MCA) pipeline via DuckDB.
    Filters candidate buildings based on exclusion masks, road proximity, and priority ranks.
    """
    print("\n==================================================")
    print(" [Stage 3/3] Running Spatial MCA Analysis in DuckDB...")
    print("==================================================")

    # Determine if intermediate data export is required
    if export_intermediates is None:
        export_debug = getattr(config, "EXPORT_INTERMEDIATE", False)
    else:
        export_debug = export_intermediates

    # Initialize DuckDB session and leverage multi-threading capabilities
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(f"PRAGMA threads={config.NUM_THREADS if hasattr(config, 'NUM_THREADS') else 8};")

    # Define paths based on centralized configuration
    gpkg_temp_output_path = config.DEBUG_DIR / "spatial_analysis_debug.gpkg"
    gpkg_output_path = config.FINAL_RESULTS / "mca_final_selections.gpkg"
    csv_output_path = config.FINAL_RESULTS / "mca_final_selections.csv"

    # Clear debug file if export is enabled and file exists
    if export_debug and gpkg_temp_output_path.exists():
        gpkg_temp_output_path.unlink()

    def _export_table_to_gpkg(table_name: str):
        """Helper function to pipe active DuckDB tables into GeoPackage layers."""
        sql = f"SELECT * FROM {table_name}"
        # Convert DuckDB relation to Arrow, then to GeoPandas dataframe for GPKG storage
        gdf = gpd.GeoDataFrame.from_arrow(con.execute(sql).arrow(), geometry='geometry')
        gdf = gdf.set_crs(config.TARGET_CRS)
        gdf.to_file(gpkg_temp_output_path, driver="GPKG", layer=table_name, mode="a")

    # ========================================================
    # STEP 1: Dissolved Exclusion Mask Generation
    # ========================================================
    print(" -> Step 1: Creating an exclusion mask inside the country...")
    con.execute(f"""
        CREATE OR REPLACE TABLE exclusion_mask AS 
        SELECT ST_Buffer(geometry, {config.STATION_BUFFER}) as geom
        FROM read_parquet('{config.PROCESSED_DIR}/exist_stations.parquet')
            UNION ALL
        SELECT ST_Buffer(geometry, {config.AIRPORT_BUFFER}) as geom
        FROM read_parquet('{config.PROCESSED_DIR}/airports.parquet')
            UNION ALL
        SELECT geometry as geom
        FROM read_parquet('{config.PROCESSED_DIR}/military_land.parquet');

        CREATE OR REPLACE TABLE exclusion_mask_dissolved AS 
        SELECT ST_Union_Agg(geom) as geometry                       
        FROM exclusion_mask;
    """)

    if export_debug:
        _export_table_to_gpkg('exclusion_mask_dissolved')

    # ========================================================
    # STEP 2.1: Pre-filtering and Boundary Clipping
    # ========================================================
    print(" -> Step 2.1: Pre-filtering and clipping buildings to the KSA border...")
    con.execute(f"""
        CREATE OR REPLACE TABLE temp_ksa_buildings AS 
        SELECT DISTINCT b.type, b.geometry
        FROM read_parquet('{config.PROCESSED_DIR}/buildings.parquet') AS b 
        JOIN read_parquet('{config.PROCESSED_DIR}/ksa_boundary.parquet') AS k
            ON ST_Intersects(b.geometry, k.geometry)
        LEFT JOIN read_parquet('{config.PROCESSED_DIR}/pois.parquet') AS p
            ON ST_Intersects(b.geometry, p.geometry)
        WHERE b.type IN ('school', 'mosque', 'hospital', 'college', 'university')
           OR p.geometry IS NOT NULL;
    """)

    count_step1 = con.execute("SELECT COUNT(*) FROM temp_ksa_buildings;").fetchone()[0]
    print(f"    Potential buildings found in KSA: {count_step1}")

    if export_debug:
        _export_table_to_gpkg('temp_ksa_buildings')

    # ========================================================
    # STEP 2.2: Buffer Exclusion Overlay
    # ========================================================
    print(" -> Step 2.2: Removing buildings located within the exclusion zone...")
    con.execute("""
        CREATE OR REPLACE TABLE selected_buildings AS 
        SELECT t.*
        FROM temp_ksa_buildings t
        WHERE NOT EXISTS (
            SELECT 1 
            FROM exclusion_mask_dissolved m
            WHERE ST_Intersects(t.geometry, m.geometry)
        );
    """)

    count_buildings = con.execute("SELECT COUNT(*) FROM selected_buildings;").fetchone()[0]
    print(f"    Building count after filtering exclusion zone: {count_buildings}")

    if export_debug:
        _export_table_to_gpkg('selected_buildings')

    # ========================================================
    # STEP 3: Proximity to Transportation Network
    # ========================================================
    print(" -> Step 3: Filtering buildings based on road asset distance threshold...")
    con.execute(f"""
        CREATE OR REPLACE TABLE final_selected_buildings AS 
        SELECT sb.*
        FROM selected_buildings sb
        WHERE EXISTS (
            SELECT 1 
            FROM read_parquet('{config.PROCESSED_DIR}/roads.parquet') r
            WHERE ST_DWithin(sb.geometry, r.geometry, {config.DIST_TO_ROAD})
        );
    """)

    count_final = con.execute("SELECT COUNT(*) FROM final_selected_buildings;").fetchone()[0]
    print(f"    Final structural asset candidates matching criteria: {count_final}")

    # ========================================================
    # STEP 4: Network Priority & Baseline Distance Ranking
    # ========================================================
    print(" -> Step 4: Prioritizing candidates based on distance to existing baseline coverage...")
    con.execute(f"""
        CREATE OR REPLACE TABLE final_buildings_priority AS 
        WITH coverage AS (
            SELECT ST_Union_Agg(ST_Buffer(geometry, {config.STATION_BUFFER})) as geom
            FROM read_parquet('{config.PROCESSED_DIR}/exist_stations.parquet')
        )
        SELECT 
            b.type,
            ST_Distance(b.geometry, coverage.geom) AS dist,
            ROW_NUMBER() OVER (ORDER BY ST_Distance(b.geometry, coverage.geom) DESC) AS priority,
            b.geometry AS geometry
        FROM final_selected_buildings AS b
        CROSS JOIN coverage;
    """)

    # ========================================================
    # STEP 5: Final Production Export (GPKG & CSV)
    # ========================================================
    print(" -> Step 5: Exporting final analytical dataset to GPKG and CSV format...")

    # 5.1 Export to GeoPackage for GIS Desktop Applications
    final_arrow = con.execute("""
        SELECT type, dist, priority, geometry 
        FROM final_buildings_priority;
    """).arrow()
    gdf_final = gpd.GeoDataFrame.from_arrow(final_arrow, geometry='geometry')
    gdf_final = gdf_final.set_crs(config.TARGET_CRS)
    gdf_final.to_file(gpkg_output_path, driver="GPKG", layer="final_buildings_priority", mode="w")

    # 5.2 Export to CSV
    df_csv = gdf_final.copy()

    # Extract numerical X and Y coordinates from the geometry centroids
    centroids = df_csv.geometry.centroid
    df_csv['centroid_x'] = centroids.x
    df_csv['centroid_y'] = centroids.y

    # Drop geometry column
    df_csv = df_csv.drop(columns=['geometry'])
    df_csv.to_csv(csv_output_path, index=False)

    # Clean up temporary structural tables
    con.execute("""
        DROP TABLE IF EXISTS exclusion_mask;
        DROP TABLE IF EXISTS exclusion_mask_dissolved;
        DROP TABLE IF EXISTS temp_ksa_buildings;
        DROP TABLE IF EXISTS selected_buildings;
        DROP TABLE IF EXISTS final_selected_buildings;
        DROP TABLE IF EXISTS final_buildings_priority;
    """)

    print(f" ✅ Analysis complete. Results stored in:\n  - {gpkg_output_path}\n  - {csv_output_path}")
    return con