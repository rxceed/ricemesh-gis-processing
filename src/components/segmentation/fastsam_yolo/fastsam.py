from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from samgeo.common import raster_to_vector

from .vari_prep import preprocess_vari_geotiff

# ── Model factory ─────────────────────────────────────────────────────────

def load_fastsam(
    model_variant: str = "FastSAM-s.pt",
    device: str | None = None,
) -> tuple:
    """
    Load a FastSAM model and return (model, device) for reuse across tiles.

    Weights are downloaded on first call to ~/.cache/ultralytics/.
    Subsequent calls load from disk — no network required.

    model_variant
      "FastSAM-s.pt"  (~23 MB)   Recommended default.  Fast; good on CPU.
      "FastSAM-x.pt"  (~138 MB)  Higher quality for small/irregular objects.
    """
    try:
        #from fastsam import FastSAM as _FastSAM
        from ultralytics import YOLO
        import os
        os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    except ImportError:
        raise ImportError(
            "FastSAM requires ultralytics ≥ 8.0:\n"
            "  uv pip install 'ultralytics>=8.0'"
        )

    if device is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"Loading {model_variant} on {device}…")
    return YOLO(model_variant), device


# ── Core tiling loop (private) ────────────────────────────────────────────

def _segment_tif_with_fastsam(
    source_tif: Path,
    reference_tif: Path,
    output_dir: Path,
    model,
    device: str,
    tile_size: int,
    overlap: int,
    min_area_m2: float,
    max_area_m2: float | None,
    conf: float,
    iou: float,
    output_stem: str,
) -> tuple[Path, Path]:
    """
    Shared tiling loop used by both public entry points.

    source_tif vs reference_tif
    ───────────────────────────
    For the RGB path  : source == reference (same file).
    For the VARI path : source = colorized VARI GeoTIFF (what FastSAM reads),
                        reference = original RGB GeoTIFF (supplies spatial metadata
                        and pixel-area calculation).
    Both files are always pixel-for-pixel co-registered — no resampling occurs.

    Tile stitching strategy
    ───────────────────────
    Each tile produces masks in tile-local coordinates.
    Only the "core" region (inset by overlap//2 on each active edge) is
    written to the output raster.  The overlap fringe is discarded so that
    objects straddling a tile boundary are not duplicated.

    Nodata skipping
    ───────────────
    Tiles where >60% of pixels are solid white (stitching border) are skipped
    entirely.  This avoids wasting inference time on empty edge tiles and
    prevents FastSAM from generating spurious boundary segments at the image edge.
    """
    import cv2

    mask_path   = output_dir / f"{output_stem}_fastsam_mask.tif"
    vector_path = output_dir / f"{output_stem}_fastsam_segments.geojson"
    tmp_png     = output_dir / "_fastsam_tile_tmp.png"

    with rasterio.open(reference_tif) as ref:
        H, W      = ref.height, ref.width
        profile   = ref.profile.copy()
        transform = ref.transform
        px_m      = abs(transform.a)       # metres per pixel (square pixels assumed)
        min_px    = max(1, int(min_area_m2  / (px_m ** 2)))
        max_px    = int(max_area_m2 / (px_m ** 2)) if max_area_m2 else None

    out_mask    = np.zeros((H, W), dtype=np.uint32)
    global_id   = 0
    stride      = tile_size - overlap
    core_margin = overlap // 2

    col_starts  = list(range(0, W, stride))
    row_starts  = list(range(0, H, stride))
    total       = len(col_starts) * len(row_starts)
    done        = 0

    with rasterio.open(source_tif) as src:
        for row_off in row_starts:
            for col_off in col_starts:
                done += 1

                # Clamp to image bounds; shift start back for edge tiles so
                # every tile is exactly tile_size × tile_size.
                col_end   = min(col_off + tile_size, W)
                row_end   = min(row_off + tile_size, H)
                col_start = max(0, col_end - tile_size)
                row_start = max(0, row_end - tile_size)
                actual_w  = col_end - col_start
                actual_h  = row_end - row_start

                print(
                    f"  [{done}/{total}]  "
                    f"col={col_start}–{col_end}  row={row_start}–{row_end}"
                )

                win   = Window(col_start, row_start, actual_w, actual_h)
                bands = np.stack(
                    [src.read(i + 1, window=win) for i in range(min(3, src.count))],
                    axis=-1,
                )  # (H, W, 3) uint8

                # Skip predominantly-nodata tiles (stitching border)
                is_white = np.all(bands > 250, axis=-1)
                if is_white.mean() > 0.60:
                    print(f"    → skipped ({100 * is_white.mean():.0f}% nodata border)")
                    continue

                # FastSAM expects a file path, not an in-memory array
                cv2.imwrite(
                    str(tmp_png),
                    cv2.cvtColor(bands, cv2.COLOR_RGB2BGR),
                )

                # ── Inference ─────────────────────────────────────────────
                try:
                    results = model.predict(
                        source=str(tmp_png),
                        device=device,
                        conf=conf,
                        #iou=iou,
                        retina_masks=True,   # full-resolution masks — essential
                        #imgsz=tile_size,     # inference resolution
                        #verbose=True,
                    )
                except Exception as exc:
                    print(f"    → FastSAM failed: {exc}")
                    continue
                
                if results is None:
                    continue
                if results[0].masks is None:
                    print("    → no masks returned")
                    continue
                for r in results:
                    r.save(filename=output_dir / f"tile/_fastsam_debug{done}.jpg")

                # masks tensor: (N, H, W) float — threshold sigmoid output
                raw_masks = results[0].masks.data.cpu().numpy()
                masks     = raw_masks > 0.5

                # ── Area filter + stitch into output raster ────────────────
                core_r0 = core_margin if row_start > 0 else 0
                core_r1 = actual_h - core_margin if row_end < H else actual_h
                core_c0 = core_margin if col_start > 0 else 0
                core_c1 = actual_w - core_margin if col_end < W else actual_w

                for mask_bool in masks:
                    # Resize to tile dims if FastSAM returned a different shape
                    # (can happen when imgsz != actual tile size)
                    if mask_bool.shape != (actual_h, actual_w):
                        mask_bool = cv2.resize(
                            mask_bool.astype(np.uint8),
                            (actual_w, actual_h),
                            interpolation=cv2.INTER_NEAREST,
                        ).astype(bool)

                    px_count = int(mask_bool.sum())
                    if px_count < min_px:
                        continue
                    if max_px is not None and px_count > max_px:
                        continue

                    global_id += 1

                    core_tile = mask_bool[core_r0:core_r1, core_c0:core_c1]
                    core_out  = np.zeros_like(core_tile, dtype=np.uint32)
                    core_out[core_tile] = global_id

                    dst_r0 = row_start + core_r0
                    dst_r1 = row_start + core_r1
                    dst_c0 = col_start + core_c0
                    dst_c1 = col_start + core_c1

                    existing = out_mask[dst_r0:dst_r1, dst_c0:dst_c1]
                    out_mask[dst_r0:dst_r1, dst_c0:dst_c1] = np.where(
                        core_out > 0, core_out, existing
                    )

    if tmp_png.exists():
        tmp_png.unlink()

    print(f"\nTotal segments (pre-filter): {global_id}")

    out_profile = profile.copy()
    out_profile.update(count=1, dtype="uint32", driver="GTiff", compress="lzw", nodata=0)

    with rasterio.open(mask_path, "w", **out_profile) as dst:
        dst.write(out_mask, 1)
    print(f"Mask   → {mask_path}")

    raster_to_vector(str(mask_path), str(vector_path))
    print(f"Vector → {vector_path}")

    return mask_path, vector_path


# ── Public entry points ───────────────────────────────────────────────────

def segment_orthophoto_fastsam_rgb(
    orthophoto_path: Path,
    output_dir: Path,
    tile_size: int = 1024,
    overlap: int = 128,
    min_area_m2: float = 100.0,
    max_area_m2: float | None = None,
    model_variant: str = "FastSAM-s.pt",
    conf: float = 0.4,
    iou: float = 0.9,
) -> tuple[Path, Path]:
    """
    Segment from raw RGB GeoTIFF.

    Use when the visual contrast between rice and surrounding land cover
    is already strong — typically at the vegetative peak stage when the
    canopy is dense and uniformly bright green.

    conf = 0.4
      Paddy plots are large and texturally uniform, so FastSAM assigns
      moderate-to-high confidence.  Lower to 0.25 to recover plots under
      thin cloud shadow or at crop margins.

    iou = 0.9
      High IOU keeps overlapping masks near tile edges.  Lower to 0.7
      if one plot is consistently split into multiple segments.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    model, device = load_fastsam(model_variant)

    return _segment_tif_with_fastsam(
        source_tif    = orthophoto_path,
        reference_tif = orthophoto_path,
        output_dir    = output_dir,
        model         = model,
        device        = device,
        tile_size     = tile_size,
        overlap       = overlap,
        min_area_m2   = min_area_m2,
        max_area_m2   = max_area_m2,
        conf          = conf,
        iou           = iou,
        output_stem   = orthophoto_path.stem,
    )


def segment_orthophoto_fastsam_vari(
    orthophoto_path: Path,
    output_dir: Path,
    tile_size: int = 1024,
    overlap: int = 128,
    min_area_m2: float = 100.0,
    max_area_m2: float | None = None,
    model_variant: str = "FastSAM-s.pt",
    conf: float = 0.35,
    iou: float = 0.9,
    band_indices: dict[str, int] | None = None,
) -> tuple[Path, Path]:
    """
    Compute VARI from RGB, then segment the colorized VARI image.

    Why VARI preprocessing helps FastSAM
    ─────────────────────────────────────
    Raw RGB: rice, grass, trees, and shrubs all share similar green hues.
             FastSAM sees them as one continuous textured region.
    VARI colorized:
      Rice plots  (VARI 0.2–0.5)  → bright saturated green
      Bunds/roads (VARI ~0.0)     → yellow-orange
      Water channels (VARI < 0)   → red
    The colour step-changes at object boundaries give FastSAM clear
    edges to segment against, regardless of the semantic content.

    conf = 0.35 (lower than RGB default)
    VARI imagery is not in FastSAM's training distribution (it was
    trained on natural photos).  A slightly lower threshold compensates
    for reduced detector confidence on this out-of-distribution input.
    Raise to 0.45 if non-plot objects (buildings, trees) are over-retained.

    Intermediate VARI GeoTIFF is written to output_dir and deleted on success.
    """
    if band_indices is None:
        band_indices = {"red": 0, "green": 1, "blue": 2}

    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: build a georeferenced VARI visualisation GeoTIFF
    vari_tif = output_dir / f"{orthophoto_path.stem}_vari_viz.tif"
    preprocess_vari_geotiff(orthophoto_path, vari_tif, band_indices)

    # Step 2: run FastSAM on the colourized image;
    #         georeference comes from the original orthophoto
    model, device = load_fastsam(model_variant)
    mask_path, vector_path = _segment_tif_with_fastsam(
        source_tif    = vari_tif,
        reference_tif = orthophoto_path,
        output_dir    = output_dir,
        model         = model,
        device        = device,
        tile_size     = tile_size,
        overlap       = overlap,
        min_area_m2   = min_area_m2,
        max_area_m2   = max_area_m2,
        conf          = conf,
        iou           = iou,
        output_stem   = orthophoto_path.stem,
    )

    # Step 3: clean up
    #vari_tif.unlink(missing_ok=True)

    return mask_path, vector_path