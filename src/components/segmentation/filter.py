from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import shapes
import geopandas as gpd

from .bbox import export_bboxes

# ─────────────────────────────────────────────────────────────────────────
# NEW — VARI + Otsu classifier for RGB drone orthophotos
# ─────────────────────────────────────────────────────────────────────────

def filter_and_classify_segments_vari(
    sam_mask_tif: Path,
    raw_rgb_tif: Path,
    output_dir: Path,
    vari_threshold: float = 0.10,
    water_fraction_threshold: float = 0.30,
) -> tuple[Path, Path, Path, Path]:
    """
    Classify SAM segments into farm plots and irrigation channels.

    Replaces EVI → VARI
    ───────────────────
    EVI requires NIR. Drone orthophotos carry only R, G, B.
    VARI = (G-R)/(G+R-B) is the strongest vegetation proxy available
    from RGB alone. A segment is a plot candidate when mean VARI > vari_threshold.

    Replaces fixed NDWI → Otsu adaptive threshold
    ──────────────────────────────────────────────
    Fixed thresholds need re-tuning per scene (different lighting, crop stage,
    camera white balance). Otsu's method automatically finds the VARI value
    that best separates the scene's bimodal histogram:

        peak A  — vegetated pixels      (rice canopy, VARI high)
        peak B  — non-vegetated pixels  (water, bunds, roads, VARI low)

    For each segment we compute the fraction of its pixels that fall below
    the Otsu threshold (i.e. are "non-vegetated").  A segment is classified
    as an irrigation channel when this fraction exceeds water_fraction_threshold.
    This is self-calibrating: the threshold adapts to the scene rather than
    requiring manual adjustment between flights or seasons.

    Parameters
    ----------
    sam_mask_tif             : uint32 segment-ID raster from FastSAM.
    raw_rgb_tif              : Original RGB GeoTIFF (to compute VARI + Otsu).
                               Does NOT need to be the same resolution as the mask
                               if they share the same CRS/extent — rasterio reads
                               the window by row/col, so identical pixel grids are
                               assumed (standard for same-source masks).
    vari_threshold           : Minimum mean segment VARI to qualify as a plot.
                               0.10 is permissive — catches early vegetative stage.
                               Raise to 0.20 for peak season when you want fewer
                               false positives from low-density vegetation.
    water_fraction_threshold : Fraction of sub-Otsu pixels to classify as irrigation.
                               0.30: ≥30% non-vegetated pixels → irrigation.
                               Lower (0.15) catches narrow channels; raise (0.45) if
                               heavily shaded plots are mis-classified as channels.

    Returns
    -------
    plot_tif, plot_bbox_geojson, irrigation_tif, irrigation_bbox_geojson
    """
    from skimage.filters import threshold_otsu

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = sam_mask_tif.stem.replace("_fastsam_mask", "").replace("_mask", "")

    # ── Load SAM mask ──────────────────────────────────────────────────────
    with rasterio.open(sam_mask_tif) as src_mask:
        mask      = src_mask.read(1)        # (H, W) uint32 segment IDs
        profile   = src_mask.profile
        transform = src_mask.transform
        crs       = src_mask.crs

    # ── Load RGB and compute VARI ──────────────────────────────────────────
    with rasterio.open(raw_rgb_tif) as src_rgb:
        red       = src_rgb.read(1).astype(np.float32)
        green     = src_rgb.read(2).astype(np.float32)
        blue      = src_rgb.read(3).astype(np.float32)
        all_bands = src_rgb.read()                      # (C, H, W)

    # Nodata detection (white / black stitching border)
    max_val  = float(np.iinfo(all_bands.dtype).max
                    if np.issubdtype(all_bands.dtype, np.integer) else 1.0)
    nodata   = (np.all(all_bands > 0.98 * max_val, axis=0) |
                np.all(all_bands < 0.02 * max_val, axis=0))

    # VARI — clip to [-1, 1]; NaN where denominator is unstable or nodata
    denom    = green + red - blue
    epsilon  = 0.02 * (max_val or 1.0)
    stable   = np.abs(denom) >= epsilon
    vari     = np.full_like(red, np.nan)
    vari[stable] = (green[stable] - red[stable]) / denom[stable]
    vari     = np.clip(vari, -1.0, 1.0)
    vari[nodata] = np.nan

    # ── Otsu threshold on valid VARI pixels ────────────────────────────────
    # threshold_otsu builds a histogram of valid pixels and returns the
    # intensity that maximises between-class variance — i.e. the best
    # separator between the two dominant pixel populations in the scene.
    # We use it as an adaptive proxy for "is this pixel vegetated?"
    valid_vari  = vari[~np.isnan(vari)]
    if valid_vari.size < 100:
        # Fallback: scene has almost no valid pixels (edge case)
        otsu_thresh = vari_threshold
        print("Warning: too few valid VARI pixels for Otsu — using vari_threshold as fallback")
    else:
        otsu_thresh = float(threshold_otsu(valid_vari))

    # water_proxy: pixels below Otsu = non-vegetated (water, bare soil, roads, bunds)
    water_proxy = (vari < otsu_thresh) & ~nodata     # (H, W) bool

    print(f"Otsu VARI threshold  : {otsu_thresh:.4f}")
    print(f"Non-vegetated pixels : {water_proxy.sum():,} "
          f"({100 * water_proxy.mean():.1f}% of scene)")

    # ── Guard: empty mask ──────────────────────────────────────────────────
    if mask.max() == 0:
        print("Warning: SAM mask contains no segments — returning empty outputs")
        empty_tif  = output_dir / f"{stem}_plot_mask.tif"
        empty_bbox = output_dir / f"{stem}_plot_bbox.geojson"
        with rasterio.open(empty_tif, "w", **profile) as dst:
            dst.write(np.zeros_like(mask), 1)
        return empty_tif, empty_bbox, empty_tif, empty_bbox

    # ── Zonal statistics (vectorised with np.bincount) ─────────────────────
    # bincount is O(N) and avoids any Python loop over segments.
    # We use the valid-pixel mask so nodata border pixels don't skew means.
    valid_pixels = (mask > 0) & ~nodata
    flat_ids     = mask[valid_pixels].astype(np.int64)

    n_segs = int(flat_ids.max()) + 1

    counts        = np.bincount(flat_ids, minlength=n_segs)
    sum_vari      = np.bincount(flat_ids,
                                weights=vari[valid_pixels],
                                minlength=n_segs)
    sum_water     = np.bincount(flat_ids,
                                weights=water_proxy[valid_pixels].astype(np.float64),
                                minlength=n_segs)

    valid_counts   = counts > 0
    safe_counts    = np.maximum(counts, 1)
    mean_vari_seg  = np.where(valid_counts, sum_vari  / safe_counts, 0.0)
    water_fraction = np.where(valid_counts, sum_water / safe_counts, 0.0)

    # ── Classification ────────────────────────────────────────────────────
    #
    # Irrigation : high fraction of sub-Otsu (non-vegetated) pixels.
    #              These are segments containing water channels, bunds, or
    #              linear non-crop features detected within the field.
    #
    # Plot       : mean VARI above threshold AND not primarily a water segment.
    #              A segment cannot be both — irrigation takes priority because
    #              a narrow channel adjacent to a plot can share pixels with it.
    #
    # Neither    : low VARI AND low water fraction → buildings, roads, tree
    #              canopy.  Discarded by having no lookup entry.
    is_irrigation = (water_fraction > water_fraction_threshold) & valid_counts
    is_plot       = (mean_vari_seg  > vari_threshold           ) & ~is_irrigation & valid_counts

    print(f"Farm plots     : {int(is_plot.sum())}")
    print(f"Irrigation segs: {int(is_irrigation.sum())}")

    # ── Build output mask arrays via lookup ───────────────────────────────
    seg_ids            = np.arange(n_segs, dtype=mask.dtype)
    plot_lookup        = np.zeros(n_segs, dtype=mask.dtype)
    irrigation_lookup  = np.zeros(n_segs, dtype=mask.dtype)
    plot_lookup[is_plot]             = seg_ids[is_plot]
    irrigation_lookup[is_irrigation] = seg_ids[is_irrigation]

    plot_mask_arr  = plot_lookup[mask]
    irrig_mask_arr = irrigation_lookup[mask]

    # ── Write GeoTIFFs ────────────────────────────────────────────────────
    plot_tif  = output_dir / f"{stem}_plot_mask.tif"
    irrig_tif = output_dir / f"{stem}_irrigation_mask.tif"

    with rasterio.open(plot_tif,  "w", **profile) as dst: dst.write(plot_mask_arr,  1)
    with rasterio.open(irrig_tif, "w", **profile) as dst: dst.write(irrig_mask_arr, 1)

    # ── Vectorise and export bounding boxes ──────────────────────────────
    def _to_geojson(arr: np.ndarray, path: Path) -> None:
        feats = [
            {"properties": {"value": int(v)}, "geometry": s}
            for s, v in shapes(arr, mask=arr > 0, transform=transform)
        ]
        if feats:
            gpd.GeoDataFrame.from_features(feats, crs=crs).to_file(path, driver="GeoJSON")

    plot_base  = output_dir / f"{stem}_plot_base.geojson"
    irrig_base = output_dir / f"{stem}_irrigation_base.geojson"
    plot_bbox  = output_dir / f"{stem}_plot_bbox.geojson"
    irrig_bbox = output_dir / f"{stem}_irrigation_bbox.geojson"

    if is_plot.sum() > 0:
        _to_geojson(plot_mask_arr, plot_base)
        export_bboxes(plot_base, plot_tif, plot_bbox)

    if is_irrigation.sum() > 0:
        _to_geojson(irrig_mask_arr, irrig_base)
        # Irrigation channels are thin and elongated — relax area + compactness filters
        export_bboxes(irrig_base, irrig_tif, irrig_bbox,
                    min_area_ha=0.001, min_compactness=0.01)

    for p in [plot_base, irrig_base]:
        if p.exists():
            p.unlink()

    return plot_tif, plot_bbox, irrig_tif, irrig_bbox