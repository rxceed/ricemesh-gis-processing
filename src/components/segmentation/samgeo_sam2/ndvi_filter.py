# module_filter.py
#
# Filter SAM2 segments to extract farm plot candidates using:
#   1. NDVI threshold  — identifies vegetated areas on a SINGLE date
#   2. Area filter     — removes noise and non-plot objects
#   3. Shape filter    — rice paddies are roughly rectangular/compact
#
# This is non-temporal: works on a brand-new farm because it reads
# the spectral signal of whatever is there right now.
#
# Known limitation:
#   A bare field between harvest and replanting (~30 days) will have
#   NDVI < threshold and may be missed. Mitigation: set threshold low
#   (~0.1) to catch recently tilled soil, or use the shape filter
#   as a fallback for geometrically regular low-NDVI segments.

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely import affinity


# Tunable constants — adjust to your study area
NDVI_VEGETATION_THRESHOLD = 0.15   # minimum mean NDVI to be a farm plot
                                    # 0.15 catches early-stage + bare-but-active
                                    # raise to 0.25 for peak-growth season only
MIN_AREA_HA = 0.05      # 500m² minimum — removes noise and bund fragments
MAX_AREA_HA = 10.0      # 10ha maximum — removes misidentified forests/water
MIN_COMPACTNESS = 0.15  # Polsby-Popper score — 1=circle, 0=very elongated
                        # rice paddies are boxy: typically 0.3–0.8


def compute_segment_ndvi(
    segment_geom,
    ndvi: np.ndarray,   # (H, W) float32 array
    profile: dict,      # rasterio profile with transform
) -> float:
    """
    Compute mean NDVI within a segment polygon.
    Uses rasterio.mask to extract only pixels inside the polygon.
    """
    with rasterio.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", count=1, dtype=np.float32,
            height=ndvi.shape[0], width=ndvi.shape[1],
            crs=profile["crs"], transform=profile["transform"],
        ) as dataset:
            dataset.write(ndvi[np.newaxis, ...])

        with memfile.open() as dataset:
            try:
                out_image, _ = rio_mask(
                    dataset, [mapping(segment_geom)],
                    crop=True, nodata=np.nan,
                )
                values = out_image[~np.isnan(out_image)]
                return float(np.mean(values)) if len(values) > 0 else 0.0
            except Exception:
                return 0.0


def polsby_popper(geom) -> float:
    """
    Polsby-Popper compactness score = 4π × Area / Perimeter².
    Score of 1 = perfect circle, lower = more irregular/elongated.
    Rice paddy plots are typically 0.3–0.8.
    """
    area = geom.area
    perimeter = geom.length
    if perimeter == 0:
        return 0.0
    return (4 * np.pi * area) / (perimeter ** 2)


def filter_farm_plots(
    segments_vector: Path,     # GeoJSON or GPKG from SAM2
    sr_tif_path: Path,         # SR GeoTIFF (to compute pixel area in m²)
    ndvi: np.ndarray,          # (H, W) from module_sam_prep
    profile: dict,
    output_path: Path,
    ndvi_threshold: float = NDVI_VEGETATION_THRESHOLD,
    min_area_ha: float = MIN_AREA_HA,
    max_area_ha: float = MAX_AREA_HA,
    min_compactness: float = MIN_COMPACTNESS,
) -> gpd.GeoDataFrame:
    """
    Filter SAM2 segments to extract farm plot polygons.

    Steps:
    1. Load all segments
    2. Project to a metric CRS for area calculation
    3. Apply area filter
    4. Compute mean NDVI per segment
    5. Apply NDVI threshold
    6. Apply shape (compactness) filter
    7. Save and return

    Why project to metric CRS?
    GEE downloads in EPSG:4326 (degrees). Area in degrees² is meaningless.
    We reproject to the local UTM zone (e.g. EPSG:32749 for East Java)
    for accurate area and shape calculations.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect local UTM zone from the raster CRS/bounds
    with rasterio.open(sr_tif_path) as src:
        bounds = src.bounds
        center_lon = (bounds.left + bounds.right) / 2
        center_lat = (bounds.bottom + bounds.top) / 2
        utm_zone = int((center_lon + 180) / 6) + 1
        hemisphere = "north" if center_lat >= 0 else "south"
        base_epsg = 32600 if hemisphere == "north" else 32700
        utm_epsg = base_epsg + utm_zone

    gdf = gpd.read_file(segments_vector)
    gdf_utm = gdf.to_crs(epsg=utm_epsg)

    print(f"Total SAM2 segments: {len(gdf_utm)}")

    # ── Step 1: Area filter ──────────────────────────────────────────────
    gdf_utm["area_ha"] = gdf_utm.geometry.area / 10_000
    area_mask = (
        (gdf_utm["area_ha"] >= min_area_ha) &
        (gdf_utm["area_ha"] <= max_area_ha)
    )
    gdf_utm = gdf_utm[area_mask].copy()
    print(f"After area filter ({min_area_ha}–{max_area_ha} ha): {len(gdf_utm)}")

    # ── Step 2: NDVI filter ──────────────────────────────────────────────
    # Reproject geometries back to the NDVI raster's CRS for pixel sampling
    gdf_reproj = gdf_utm.to_crs(profile["crs"])
    ndvi_values = [
        compute_segment_ndvi(geom, ndvi, profile)
        for geom in gdf_reproj.geometry
    ]
    gdf_utm["mean_ndvi"] = ndvi_values

    ndvi_mask = gdf_utm["mean_ndvi"] >= ndvi_threshold
    gdf_utm = gdf_utm[ndvi_mask].copy()
    print(f"After NDVI filter (>= {ndvi_threshold}): {len(gdf_utm)}")

    # ── Step 3: Shape filter ─────────────────────────────────────────────
    gdf_utm["compactness"] = gdf_utm.geometry.apply(polsby_popper)
    shape_mask = gdf_utm["compactness"] >= min_compactness
    gdf_utm = gdf_utm[shape_mask].copy()
    print(f"After shape filter (compactness >= {min_compactness}): {len(gdf_utm)}")

    # Label confirmed farm plots
    gdf_utm["class"] = "farm_plot"
    gdf_utm["source"] = "SAM2+NDVI"

    gdf_utm.to_file(output_path, driver="GPKG")
    print(f"Farm plot polygons saved → {output_path}")
    return gdf_utm