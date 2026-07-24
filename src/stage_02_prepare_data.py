import zipfile
import shutil
import fiona
import geopandas as gpd
import src.config as config


def _process_layer(filename: str, layer_name: str, columns: list, query: str = None):
    """
    Universal helper function to process OSM layers.
    Loads from extracted Geofabrik folder, filters, updates CRS,
    exports to GeoParquet, and conditionally appends to GeoPackage.
    """
    # Point directly to the Geofabrik folder extracted during Stage 1
    raw_path = config.RAW_DIR / "geofabrik_gcc" / filename
    gpkg_path = config.DEBUG_DIR / "data_preparation_debug.gpkg"
    parquet_path = config.PROCESSED_DIR / f"{layer_name}.parquet"

    if not raw_path.exists():
        print(f" ⚠️ File not found: {filename} in 'geofabrik_gcc'. Skipping layer...")
        return None

    # 1. Read raw spatial data
    gdf = gpd.read_file(raw_path)

    # 2. Apply attribute query filter if provided
    if query:
        gdf = gdf.query(query).copy()

    # 3. Transform spatial data to target CRS
    gdf = gdf.to_crs(config.TARGET_CRS)

    # 4. Subset to required columns only
    gdf_filtered = gdf[columns].copy()

    # 5. Export clean layer to optimized GeoParquet format
    gdf_filtered.to_parquet(parquet_path, index=False)

    # 6. Append layer to GeoPackage database ONLY if EXPORT_INTERMEDIATE is True
    if getattr(config, "EXPORT_INTERMEDIATE", False):
        gdf_filtered.to_file(gpkg_path, layer=layer_name, driver="GPKG", mode="a")

    print(f" ✅ Layer '{layer_name}' processed successfully ({len(gdf_filtered)} features).")
    return len(gdf_filtered)


def run_stage_prepare():
    """Stage 2: Preprocess raw layers (KMZ & OSM) and convert them to GeoParquet format."""
    print("\n==================================================")
    print(" [Stage 2/3] Preprocessing raw layers & converting to GeoParquet...")
    print("==================================================")

    export_debug = getattr(config, "EXPORT_INTERMEDIATE", False)
    gpkg_file = config.DEBUG_DIR / "data_preparation_debug.gpkg"

    # Remove legacy verification file if debug export is ENABLED
    if export_debug and gpkg_file.exists():
        gpkg_file.unlink()

    stats = {}

    # ========================================================
    # PART 1: Process Existing CORS Stations (KMZ/KML format)
    # ========================================================
    # Enable KML driver support in Fiona
    fiona.drvsupport.supported_drivers['KML'] = 'rw'

    kmz_files = list(config.RAW_DIR.glob("*.kmz"))
    if kmz_files:
        kmz_path = kmz_files[0]
        temp_kml_dir = config.RAW_DIR / "temp_kml"

        # Extract the core KML document from inside the KMZ archive
        with zipfile.ZipFile(kmz_path, 'r') as z:
            z.extract('doc.kml', path=temp_kml_dir)

        # Read KML layer, project to target CRS, and filter columns
        stations = gpd.read_file(temp_kml_dir / "doc.kml", driver="KML", engine="fiona")
        stations = stations.to_crs(config.TARGET_CRS)
        stations_clean = stations[['Name', 'geometry']].copy()

        # Save to processed directory
        stations_clean.to_parquet(config.PROCESSED_DIR / "exist_stations.parquet", index=False)

        # Save to verification GeoPackage ONLY if enabled
        if export_debug:
            stations_clean.to_file(gpkg_file, layer="exist_stations", driver="GPKG", mode="a")

        stats["CORS Stations"] = len(stations_clean)
        print(f" ✅ KMZ Layer 'exist_stations' processed successfully ({len(stations_clean)} features).")

        # Clean up temporary extraction folder
        shutil.rmtree(temp_kml_dir)
    else:
        print(" ⚠️ No .kmz files found in raw data directory. Skipping CORS Stations...")

    # ========================================================
    # PART 2: Process OpenStreetMap (OSM) Layers
    # ========================================================
    # 1. KSA Boundary (Filter by specific country osm_id)
    stats["KSA Boundary"] = _process_layer(
        filename="gis_osm_adminareas_a_free_1.shp",
        layer_name="ksa_boundary",
        query="osm_id == '307584'",
        columns=["name", "geometry"]
    )

    # 2. Airports (Filter by airport facility class)
    stats["Airports"] = _process_layer(
        filename="gis_osm_transport_a_free_1.shp",
        layer_name="airports",
        query="fclass == 'airport'",
        columns=["name", "geometry"]
    )

    # 3. Military Land (Filter by military landuse zone restriction)
    stats["Military Land"] = _process_layer(
        filename="gis_osm_landuse_a_free_1.shp",
        layer_name="military_land",
        query="fclass == 'military'",
        columns=["name", "geometry"]
    )

    # 4. Buildings (No thematic filter required - massive dataset)
    stats["Buildings"] = _process_layer(
        filename="gis_osm_buildings_a_free_1.shp",
        layer_name="buildings",
        columns=["type", "geometry"]
    )

    # 5. Points of Interest (Filter educational and medical buffer zones)
    stats["Points of Interest"] = _process_layer(
        filename="gis_osm_pois_a_free_1.shp",
        layer_name="pois",
        query="fclass in ['college', 'hospital', 'school', 'university']",
        columns=["osm_id", "fclass", "geometry"]
    )

    # 6. Roads (No thematic filter required - transportation network)
    stats["Roads"] = _process_layer(
        filename="gis_osm_roads_free_1.shp",
        layer_name="roads",
        columns=["osm_id", "fclass", "geometry"]
    )

    # Display execution runtime summary metrics
    print("\n================ STATS ==========================")
    for layer, count in stats.items():
        if count is not None:
            print(f" {layer:<20} : {count} objects")
    print("==================================================")
    print("Data preparation complete.")