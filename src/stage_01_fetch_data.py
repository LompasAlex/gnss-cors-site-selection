import zipfile
from pathlib import Path
import urllib3
import requests
from src import config

# Suppress SSL warnings for servers with self-signed or untrusted SSL certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def download_and_unzip(
    url: str,
    output_zip_path: Path,
    extract_to_dir: Path,
    verify_ssl: bool = True,
):
    """Helper function to download and extract a zip archive.

    :param url: Remote file URL to download.
    :param output_zip_path: Local Path where the zip file should be saved.
    :param extract_to_dir: Local Path directory where files will be extracted.
    :param verify_ssl: Whether to verify SSL certificates (set False for
        untrusted SSL servers).
    """
    if not output_zip_path.exists():
        print(f"Downloading from {url}...")

        # Stream=True ensures efficient memory usage for large spatial datasets
        response = requests.get(url, stream=True, verify=verify_ssl)
        response.raise_for_status()

        # Ensure output directory exists before saving
        extract_to_dir.mkdir(parents=True, exist_ok=True)

        with open(output_zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Extracting to {extract_to_dir}...")
        with zipfile.ZipFile(output_zip_path, "r") as z:
            z.extractall(extract_to_dir)

        print(f"Successfully processed: {output_zip_path.name}")
    else:
        print(f"File {output_zip_path.name} already exists. Skipping download.")


def run_stage_fetch():
    """Download and extract raw CORS and Geofabrik spatial datasets if not present."""
    print(" [Stage 1/3] Fetching raw spatial data...")
    config.setup_directories()

    # 1. Download CORS stations data (SSL verification disabled due to portal certificate issues)
    cors_zip_path = config.RAW_DIR / "cors_stations.zip"
    download_and_unzip(
        url=config.URL_CORS,
        output_zip_path=cors_zip_path,
        extract_to_dir=config.RAW_DIR,
        verify_ssl=False,
    )

    # 2. Download OSM Geofabrik layers (GCC States region)
    geofabrik_zip_path = config.RAW_DIR / "gcc_states_geofabrik.zip"
    geofabrik_extract_dir = config.RAW_DIR / "geofabrik_gcc"

    download_and_unzip(
        url=config.URL_LAYERS,
        output_zip_path=geofabrik_zip_path,
        extract_to_dir=geofabrik_extract_dir,
        verify_ssl=False,
    )
