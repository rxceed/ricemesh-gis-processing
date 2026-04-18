import dotenv
import numpy as np
import ee
import os
import requests
from pathlib import Path

dotenv.load_dotenv()
GEE_SERVICE_EMAIL = str(os.getenv("GEE_SERVICE_EMAIL"))
GEE_SERVICE_KEY = str(os.getenv("GEE_SERVICE_KEY"))

KEY_PATH = Path.joinpath(Path.cwd(), GEE_SERVICE_KEY).resolve()

GEE_COLLECTIONS = {
    "sentinel-2-l2a": "COPERNICUS/S2_SR_HARMONIZED",
    "sentinel-1-sar": "COPERNICUS/S1_GRD"
    }

GEE_BANDS = {
    "sentinel-2-l2a-10m": ["B4", "B3", "B2", "B8"], #R, G, B, NIR
    "sentinel-2-l2a-20m": ["B5", "B6", "B7", "B8A", "B11", "B12"],
    }
GEE_BANDS["sentinel-2-l2a"] = GEE_BANDS["sentinel-2-l2a-10m"]+GEE_BANDS["sentinel-2-l2a-20m"]

# Initialize GEE credentials
def init() -> None:
    creds = ee.ServiceAccountCredentials(GEE_SERVICE_EMAIL, str(KEY_PATH))
    ee.Initialize(creds)

# Get Sentinel-2-L2A image
def get_sentinel_2_l2a(bbox:list[float], max_cloud_cover:float=0.15) -> ee.Image:
    roi = ee.Geometry.BBox(*bbox)
    def mask_s2_clouds(image):
        """Use the SCL band to mask clouds and cloud shadows."""
        scl = image.select("SCL")
        # SCL values: 3=cloud shadow, 8=cloud medium, 9=cloud high, 10=cirrus
        cloud_mask = (
            scl.neq(3)
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10))
        )
        return image.updateMask(cloud_mask)
    image = (
        ee.ImageCollection(GEE_COLLECTIONS["sentinel-2-l2a"])
        .filterBounds(roi)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover * 100))
        .map(mask_s2_clouds)
        .limit(1, "system:time_start", False)
        .mean()
        .clip(roi)
        )
    return image

def generate_bbox_grid(
    bbox: list[float],
    tile_deg: float = 0.05,   # degrees per tile side (~5km at equator)
    overlap_deg: float = 0.005,
) -> list[list[float]]:
    """
    Split a large bounding box into a grid of smaller bboxes.

    Why tile at the download stage instead of post-download?
    GEE's getDownloadURL has a size limit per call. By requesting
    small tiles directly, we stay within limits AND produce
    ready-to-use tiles that match Module 2's expected input.
    No need to tile after download.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    tiles = []
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            tile_bbox = [
                lon,
                lat,
                min(lon + tile_deg, max_lon),
                min(lat + tile_deg, max_lat),
            ]
            tiles.append(tile_bbox)
            lon += tile_deg - overlap_deg
        lat += tile_deg - overlap_deg
    return tiles

# Download the image in .geotiff format
def download_geotiff(
    image: ee.Image,
    bands: list[str],
    bbox: list[float],
    output_path: Path,
    scale: int = 10,          # meters per pixel
    crs: str = "EPSG:4326",
) -> None:
    region = ee.Geometry.BBox(*bbox)
    url = image.select(bands).getDownloadURL({
        "region": region,
        "scale": scale,
        "crs": crs,
        "format": "GEO_TIFF",
        "filePerBand": False,   # single multi-band GeoTIFF
    })
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Downloaded: {output_path}")

def fetch_tiles(
    bbox: list[float],
    output_dir: Path,
    source: str = "sentinel-2-l2a",
    bands: list[str] = None,
    max_cloud_cover: float = 0.15,
    scale: int = 10,
    tile_deg: float = 0.05,
) -> list[Path]:
    """
    Main function: replaces module_01_data_access.py entirely.
    Downloads a grid of GeoTIFF tiles into output_dir.
    Returns list of downloaded file paths for Module 2 to consume.

    Choosing scale:
    - NICFI → use scale=4 or scale=5 (native ~4.77m)
    - Sentinel-2 → use scale=10 (native 10m)
    - Requesting finer than native res wastes bandwidth, no detail gained
    """
    if bands == None:
        bands = GEE_BANDS[source]

    output_dir.mkdir(parents=True, exist_ok=True)
    tile_bboxes = generate_bbox_grid(bbox, tile_deg=tile_deg)
    print(f"Downloading {len(tile_bboxes)} tiles from GEE ({source})...")

    downloaded = []

    for i, tile_bbox in enumerate(tile_bboxes):
        out_path = output_dir / f"tile_{i:04d}.tif"
        
        """
        if out_path.exists():
            print(f"  tile {i:04d} already exists, skipping")
            downloaded.append(out_path)
            continue
        """

        try:
            image = get_sentinel_2_l2a(tile_bbox, max_cloud_cover)

            download_geotiff(
                image=image,
                bands=bands,
                bbox=tile_bbox,
                output_path=out_path,
                scale=scale,
            )
            downloaded.append(out_path)

        except Exception as e:
            # A tile might fail if GEE has no data for that bbox.
            # Log and continue — don't abort the whole batch.
            print(f"  tile {i:04d} failed: {e}")

    print(f"Done. {len(downloaded)}/{len(tile_bboxes)} tiles downloaded.")
    return downloaded
