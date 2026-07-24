from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Paths
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DEBUG_DIR = BASE_DIR / "data" / "debug"
FINAL_RESULTS = BASE_DIR / "results"

# Spatial Analysis Parameters
TARGET_CRS = "EPSG:3857"
STATION_BUFFER = 35000      # 35 km
AIRPORT_BUFFER = 5000       # 5 km
DIST_TO_ROAD = 20           # 20 meters

NUM_THREADS = 8
EXPORT_INTERMEDIATE = True

# External URLs
URL_CORS = "https://ksacors.geoportal.sa/WelcomePage/KSA-CORS%20Location%20(Approximate).zip"
URL_LAYERS = "https://download.geofabrik.de/asia/gcc-states-latest-free.shp.zip"

def setup_directories():
    for folder in [RAW_DIR, PROCESSED_DIR, DEBUG_DIR,FINAL_RESULTS]:
        folder.mkdir(parents=True, exist_ok=True)