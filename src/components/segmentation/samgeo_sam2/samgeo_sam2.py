import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pathlib import Path
from skimage import exposure
from samgeo import SamGeo2
from samgeo.common import raster_to_vector 
import matplotlib.cm as cm
import matplotlib.colors as mcolors

def load_sr_bands(tif_path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.open(tif_path) as src:
        data = src.read().astype(np.float32)       # (C, H, W)

        # dataset_mask(): 0=masked/nodata, 255=valid — same shape as one band
        mask_255 = src.dataset_mask()              # (H, W) uint8
        valid_mask = (mask_255 == 255)             # (H, W) bool

        # Catch explicit nodata value if set
        if src.nodata is not None:
            nodata_val = src.nodata
            for c in range(data.shape[0]):
                valid_mask &= (data[c] != nodata_val)

        profile = src.profile
    return data, valid_mask, profile

def compute_ndvi(bands: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """bands: (4,H,W) order [Red=0, Green=1, Blue=2, NIR=3]"""
    red = bands[0].astype(np.float64)
    nir = bands[3].astype(np.float64)
    ndvi = np.where(
        valid_mask,
        (nir - red) / (nir + red + 1e-8),
        np.nan,
    )
    return np.clip(ndvi, -1.0, 1.0).astype(np.float32)

def fill_nodata(bands: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """
    Fill nodata pixels with the mean of valid pixels per band.

    Why fill instead of just masking?
    The false-color composite needs to cover the full pixel grid — SAM2
    doesn't handle masked arrays, it expects a dense uint8 image.
    Filling with the band mean keeps the histogram stable and means
    nodata areas render as a neutral mid-grey instead of black or white,
    which prevents SAM2 from creating phantom segments at nodata edges.
    """
    filled = bands.copy()
    for c in range(bands.shape[0]):
        valid_pixels = bands[c][valid_mask]
        if len(valid_pixels) == 0:
            continue
        fill_value = float(np.mean(valid_pixels))
        filled[c][~valid_mask] = fill_value
    return filled


def normalize_band(
    band: np.ndarray,
    valid_mask: np.ndarray,
    p_low: float = 2.0,
    p_high: float = 98.0,
) -> np.ndarray:
    """
    Percentile stretch to [0, 1] computed ONLY over valid pixels.

    Why restrict percentiles to valid pixels?
    If nodata=0 is set and 10% of pixels are nodata, the p2 percentile
    of the whole image is 0 (the nodata value itself), so the stretch
    denominator collapses and everything clamps to 1.0 — the image
    turns solid white. Computing percentiles only over valid pixels
    avoids this entirely.
    """
    valid_pixels = band[valid_mask]
    if len(valid_pixels) == 0:
        return np.zeros_like(band)
    lo = np.percentile(valid_pixels, p_low)
    hi = np.percentile(valid_pixels, p_high)
    if hi - lo < 1e-8:
        return np.zeros_like(band)
    return np.clip((band - lo) / (hi - lo), 0.0, 1.0)

def build_falsecolor_composite(
    bands: np.ndarray,
    valid_mask: np.ndarray,
    use_clahe: bool = False,
    p_low: float = 2.0,
    p_high: float = 98.0,
) -> np.ndarray:
    """
    NIR false-color composite for SAM2.
    Display: [R=NIR, G=Red, B=Green]

    Nodata pixels are filled with band mean before normalization,
    so there are no transparent holes in the output.
    """
    # Fill nodata before normalizing so they don't skew the stretch
    filled = fill_nodata(bands, valid_mask)

    nir   = normalize_band(filled[3], valid_mask, p_low, p_high)
    red   = normalize_band(filled[0], valid_mask, p_low, p_high)
    green = normalize_band(filled[1], valid_mask, p_low, p_high)

    composite_hwc = np.stack([nir, red, green], axis=-1)  # (H, W, 3) float [0,1]

    if use_clahe:
        from skimage import exposure
        for i in range(3):
            composite_hwc[..., i] = exposure.equalize_adapthist(
                composite_hwc[..., i], clip_limit=0.01
            )

    return (composite_hwc * 255).astype(np.uint8)

def build_ndvi_colormap_composite(
    ndvi: np.ndarray,
    valid_mask: np.ndarray,
    vmin: float = -0.1,   # values below this map to the "red" end
    vmax: float = 0.8,    # values above this map to the "green" end
) -> np.ndarray:
    """
    Render NDVI as a 3-channel uint8 image using the RdYlGn colormap.

    Why RdYlGn?
    Red = low NDVI (buildings, roads, bare soil, water)
    Yellow = transition zone (sparse vegetation, fallow fields)
    Green = high NDVI (active crops, dense vegetation)

    Farm plots will be a distinct green blob surrounded by red/yellow
    non-vegetation. SAM2 will segment "green region" cleanly because
    the color boundary is sharp and high-contrast — exactly what it
    was trained on.

    vmin=-0.1 rather than 0:
    Including slightly negative NDVI ensures water bodies (NDVI ~ -0.2
    to -0.05) map to deep red and are clearly separated from bare soil
    (NDVI ~ 0.0 to 0.15, which maps to yellow). This prevents SAM2
    from merging canals with adjacent dry fields.

    vmax=0.8:
    Rice paddy at peak growth is typically 0.55–0.75. Setting vmax=0.8
    spreads the active vegetation range across most of the green spectrum
    so SAM2 sees internal texture variation within the field, which
    helps it find sub-field boundaries (individual plot edges).
    """
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    colormap = cm.get_cmap("RdYlGn")

    # Fill NaN (nodata) with neutral mid value before colorizing
    ndvi_filled = ndvi.copy()
    ndvi_filled[~valid_mask] = 0.0
    ndvi_filled = np.nan_to_num(ndvi_filled, nan=0.0)

    # Apply colormap: returns (H, W, 4) RGBA float [0,1]
    colored = colormap(norm(ndvi_filled))   # (H, W, 4)

    # Drop alpha channel, convert to uint8
    rgb_uint8 = (colored[..., :3] * 255).astype(np.uint8)

    # Set nodata pixels to mid-grey so SAM2 doesn't create edge segments
    # at the tile boundary where valid data meets nodata
    rgb_uint8[~valid_mask] = 128

    return rgb_uint8


def sam_prep_nir(
    sr_tif_path: Path,
    output_vis_path: Path,   # saves a georeferenced 3-band uint8 TIF
    use_clahe: bool = False
) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Full preparation pipeline:
    1. Load SR bands
    2. Compute NDVI (saved separately for post-filtering)
    3. Build false-color composite for SAM2

    Returns:
        composite_hwc: (H, W, 3) uint8 — feed this to SAM2
        ndvi:          (H, W) float32 — use this to filter segments after SAM2
        profile:       rasterio profile with updated transform (2.5m pixels)
    """
    bands, valid_mask, profile = load_sr_bands(sr_tif_path)
    n_invalid = int(np.sum(~valid_mask))
    n_total   = valid_mask.size
    print(f"SR band value range : [{bands.min():.4f}, {bands.max():.4f}]")
    print(f"NoData pixels       : {n_invalid} / {n_total} "
          f"({100 * n_invalid / n_total:.2f}%)")
    ndvi = compute_ndvi(bands)
    composite = build_falsecolor_composite(bands, valid_mask, use_clahe)

    # Save as georeferenced 3-band uint8 TIF so samgeo can read it
    # (samgeo expects a file path, not a numpy array)
    out_profile = profile.copy()
    out_profile.update(count=3, dtype=np.uint8, driver="GTiff")

    output_vis_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_vis_path, "w", **out_profile) as dst:
        dst.write(composite.transpose(2, 0, 1))   # (3, H, W)

    print(f"SAM2 input saved: {output_vis_path}")
    return composite, ndvi, profile

def sam_prep_ndvi(
    sr_tif_path: Path,
    output_vis_path: Path,         # primary: NDVI colormap — feed to SAM2
    output_falsecolor_path: Path | None = None,  # optional: NIR composite for visual QC
    ndvi_vmin: float = -0.1,
    ndvi_vmax: float = 0.8,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Prepare SR GeoTIFF for SAM2 segmentation.

    Primary output (output_vis_path):
        NDVI colorized as RdYlGn — this is what SAM2 receives.

    Optional output (output_falsecolor_path):
        NIR false-color composite — for human visual inspection only.
        Do NOT feed this to SAM2 anymore.

    Returns:
        ndvi_colormap : (H, W, 3) uint8 — SAM2 input
        ndvi          : (H, W) float32  — for post-segmentation filtering
        profile       : source rasterio profile
    """
    bands, valid_mask, profile = load_sr_bands(sr_tif_path)

    n_invalid = int(np.sum(~valid_mask))
    print(f"SR value range  : [{bands.min():.4f}, {bands.max():.4f}]")
    print(f"NoData pixels   : {n_invalid}/{valid_mask.size} "
        f"({100*n_invalid/valid_mask.size:.2f}%)")

    ndvi          = compute_ndvi(bands, valid_mask)
    ndvi_colormap = build_ndvi_colormap_composite(ndvi, valid_mask, ndvi_vmin, ndvi_vmax)

    valid_ndvi = ndvi[valid_mask]
    print(f"NDVI range      : [{np.nanmin(valid_ndvi):.3f}, {np.nanmax(valid_ndvi):.3f}]")
    print(f"NDVI > 0.2      : {100*np.mean(valid_ndvi > 0.2):.1f}% of valid pixels")

    base_profile = profile.copy()
    base_profile.update(count=3, dtype=np.uint8, driver="GTiff",
                        compress="lzw", nodata=None)

    output_vis_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_vis_path, "w", **base_profile) as dst:
        dst.write(ndvi_colormap.transpose(2, 0, 1))
        dst.update_tags(1, description="NDVI colorized RdYlGn R channel")
        dst.update_tags(2, description="NDVI colorized RdYlGn G channel")
        dst.update_tags(3, description="NDVI colorized RdYlGn B channel")

    print(f"SAM2 input (NDVI colormap) → {output_vis_path}")

    # Optionally also save the false-color composite for visual QC
    if output_falsecolor_path is not None:
        falsecolor = build_falsecolor_composite(bands, valid_mask)
        with rasterio.open(output_falsecolor_path, "w", **base_profile) as dst:
            dst.write(falsecolor.transpose(2, 0, 1))
        print(f"Visual QC composite        → {output_falsecolor_path}")

    return ndvi_colormap, ndvi, profile

def run_sam2_automatic(
    input_vis_tif: Path,     # the false-color uint8 GeoTIFF from module_sam_prep
    output_mask_tif: Path,   # raster masks (each segment = unique int ID)
    output_vector_path: Path,# vector output (.gpkg or .geojson)
) -> Path:
    """
    Run SAM2 in fully automatic mode — no annotations needed.

    Parameter rationale:
    points_per_side=32: places a 32×32 grid of seed points across the image.
    For a 512px tile this is one point per 16px. At 2.5m/px, one point
    per 40m ground distance — appropriate for rice paddy plots (0.1–2ha).
    Increase to 48 or 64 if small plots are being missed.
    pred_iou_thresh=0.7: minimum predicted mask quality. Lower → more masks
    but more noise. 0.7 is the practical minimum for clean field boundaries.
    stability_score_thresh=0.92: masks must be stable under slight threshold
    perturbation. High value reduces fragmented/noisy boundary masks.
    min_mask_region_area=100: ignore segments smaller than 100px² at 2.5m =
    625m². This filters out sensor noise, shadow specks, and sub-plot
    fragments. Adjust down if your plots are very small terraced fields.
    crop_n_layers=1: also run SAM on 2× cropped sub-images and merge results.
    This helps catch small objects that get missed at full image scale.
    Set to 0 to skip (faster) if your plots are large (>0.5ha).

    Why use_m2m=True?
    Mask-to-mask refinement — SAM2 refines each mask using other generated masks
    as context. Significantly improves boundary accuracy at field edges.
    """
    output_mask_tif.parent.mkdir(parents=True, exist_ok=True)

    sam2 = SamGeo2(
        model_id="sam2-hiera-large",
        automatic=True,
        apply_postprocessing=False,   # we do our own filtering
        points_per_side=48,
        points_per_batch=64,
        pred_iou_thresh=0.60,
        stability_score_thresh=0.75,
        stability_score_offset=0.70,
        crop_n_layers=0,
        box_nms_thresh=0.70,
        crop_n_points_downscale_factor=2,
        min_mask_region_area=25.0,
        use_m2m=True,
    )

    print(f"Running SAM2 on {input_vis_tif.name} ...")
    sam2.generate(str(input_vis_tif))

    # Save raster: each segment gets a unique integer ID
    sam2.save_masks(output=str(output_mask_tif), unique=True)

    # Save vector: converts raster masks to polygons
    raster_to_vector(str(output_mask_tif), str(output_vector_path))

    print(f"Segments saved: {output_mask_tif} and {output_vector_path}")
    return output_vector_path