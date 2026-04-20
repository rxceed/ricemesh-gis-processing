# module_drone_segment.py  — SamGeo2 rewrite

from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.transform import from_bounds
from samgeo import SamGeo2
from samgeo.common import raster_to_vector


# ── Model factory ─────────────────────────────────────────────────────────────

def load_sam2(device: str | None = None) -> SamGeo2:
    """
    Initialize SamGeo2 with parameters tuned for drone orthophotos.

    Why these values differ from the satellite version:
    - Drone RGB is high-contrast true color — SAM2 performs much better
    here than on satellite imagery. We don't need to fight for field
    boundaries; they're already visually sharp.
    - Fields are large objects relative to image pixels at cm resolution.
    points_per_side=32 means one seed point per ~60px² on a 512-tile.
    That's one point per ~0.3m² at 3cm GSD — plenty for paddy plots.
    - crop_n_layers=0: sub-image crops generate more small-object segments
      (individual plants, bund stones). We want field-level segments, not
      sub-field detail.
    - pred_iou_thresh=0.65 and stability_score_thresh=0.80 are deliberately
      lenient — a rice field's interior is spatially uniform, which makes
      SAM2 less "confident" about it vs a building. Too strict and every
      field gets rejected.
    """
    import torch
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading SAM2 on {device} ...")

    return SamGeo2(
        model_id="sam2-hiera-large",
        automatic=True,
        apply_postprocessing=False,
        device=device,

        points_per_side=64,
        points_per_batch=64,
        pred_iou_thresh=0.50,
        stability_score_thresh=0.60,
        stability_score_offset=0.70,
        crop_n_layers=0,
        box_nms_thresh=0.70,
        crop_n_points_downscale_factor=2,
        min_mask_region_area=300,    # px — real minimum enforced after tiling
        use_m2m=True,
    )


# ── Tile reading ──────────────────────────────────────────────────────────────

def read_tile_as_uint8(
    src: rasterio.DatasetReader,
    window: Window,
    p_low: float = 2.0,
    p_high: float = 98.0,
) -> np.ndarray:
    """
    Read a rasterio window and return a display-ready (H, W, 3) uint8 array.

    Why percentile stretch per-tile?
    Each tile may cover a slightly different tonal range (shadow vs. sunlit
    bund). Per-tile stretch ensures SAM2 always sees maximum contrast
    regardless of global image brightness, which improves boundary detection.
    """
    data = np.stack(
        [src.read(i + 1, window=window).astype(np.float32) for i in range(min(3, src.count))],
        axis=-1,
    )   # (H, W, 3)

    out = np.zeros_like(data, dtype=np.float32)
    for c in range(data.shape[2]):
        lo = np.percentile(data[..., c], p_low)
        hi = np.percentile(data[..., c], p_high)
        out[..., c] = np.clip((data[..., c] - lo) / (hi - lo + 1e-8), 0.0, 1.0)

    return (out * 255).astype(np.uint8)


# ── Tiled inference ───────────────────────────────────────────────────────────

def segment_orthophoto(
    orthophoto_path: Path,
    output_dir: Path,
    tile_size: int = 1024,
    overlap: int = 128,
    min_area_m2: float = 100.0,
    max_area_m2: float | None = None,
) -> tuple[Path, Path]:
    """
    Segment farm plots from a drone orthophoto using SamGeo2.

    Why manual tiling?
    SamGeo2 has no built-in tiled inference (that's SAM3-only). Loading a
    5000×5000+ orthophoto into SAM2's image encoder in one shot exceeds most
    GPU memory budgets. We replicate the sliding-window approach: process
    overlapping tiles, assign globally-unique segment IDs, write results into
    a single output raster, then vectorize.

    Overlap strategy:
    Each tile's output mask is split into a "core" region (center) and an
    "overlap" region (edges). Only the core is written to the output — this
    prevents the same field from appearing as two separate segments when its
    boundary falls near a tile edge.

    Returns:
        mask_path   : GeoTIFF, pixel value = unique segment ID (0 = background)
        vector_path : GeoJSON, one polygon per segment
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem        = orthophoto_path.stem
    mask_path   = output_dir / f"{stem}_mask.tif"
    vector_path = output_dir / f"{stem}_segments.geojson"

    sam = load_sam2()

    with rasterio.open(orthophoto_path) as src:
        H, W      = src.height, src.width
        profile   = src.profile.copy()
        transform = src.transform
        crs       = src.crs

        # Pixel area → convert m² thresholds to pixel counts
        px_size_m     = abs(transform.a)    # metres per pixel (square pixels assumed)
        px_area_m2    = px_size_m ** 2
        min_px        = max(1, int(min_area_m2 / px_area_m2))
        max_px        = int(max_area_m2 / px_area_m2) if max_area_m2 else None
        print(f"Pixel size    : {px_size_m:.4f} m  ({px_area_m2:.4f} m²/px)")
        print(f"Min segment   : {min_px} px  ({min_area_m2} m²)")
        print(f"Image size    : {W} × {H} px")

        # Allocate output mask in memory (uint32 supports ~4B unique segments)
        out_mask     = np.zeros((H, W), dtype=np.uint32)
        global_id    = 0          # monotonically increasing segment counter
        stride       = tile_size - overlap
        core_margin  = overlap // 2   # pixels to discard from each tile edge

        # Compute tile grid
        col_starts = list(range(0, W, stride))
        row_starts = list(range(0, H, stride))
        total_tiles = len(col_starts) * len(row_starts)
        tile_idx    = 0

        for row_off in row_starts:
            for col_off in col_starts:
                tile_idx += 1

                # Clamp window to image bounds
                col_end = min(col_off + tile_size, W)
                row_end = min(row_off + tile_size, H)
                # Shift start back if we'd produce an undersized edge tile
                col_start = max(0, col_end - tile_size)
                row_start = max(0, row_end - tile_size)

                actual_w = col_end - col_start
                actual_h = row_end - row_start
                win = Window(col_start, row_start, actual_w, actual_h)

                print(f"  Tile {tile_idx}/{total_tiles}  "
                      f"col={col_start}–{col_end}  row={row_start}–{row_end}")

                # Read + normalize
                tile_rgb = read_tile_as_uint8(src, win)

                # Save tile as a temp file (SamGeo2 expects a file path)
                tmp_tif = output_dir / "_tile_tmp.tif"
                tile_transform = src.window_transform(win)
                with rasterio.open(
                    tmp_tif, "w",
                    driver="GTiff", count=3, dtype=np.uint8,
                    height=actual_h, width=actual_w,
                    crs=crs, transform=tile_transform,
                ) as tmp:
                    tmp.write(tile_rgb.transpose(2, 0, 1))

                # Run SAM2 on this tile
                tmp_mask = output_dir / "_tile_mask_tmp.tif"
                try:
                    sam.generate(str(tmp_tif))
                    sam.save_masks(output=str(tmp_mask), unique=True)
                except Exception as e:
                    print(f"    SAM2 failed on tile {tile_idx}: {e} — skipping")
                    continue

                # Read tile mask
                with rasterio.open(tmp_mask) as msrc:
                    tile_mask = msrc.read(1).astype(np.uint32)  # (H, W)

                # Determine the "core" region within the tile
                # (discard overlap margin to avoid double-counting boundaries)
                core_r0 = core_margin if row_start > 0 else 0
                core_r1 = actual_h - core_margin if row_end < H else actual_h
                core_c0 = core_margin if col_start > 0 else 0
                core_c1 = actual_w - core_margin if col_end < W else actual_w

                # Remap tile-local segment IDs to global IDs and write core
                local_ids = np.unique(tile_mask)
                local_ids = local_ids[local_ids != 0]   # exclude background

                id_map = {}
                for lid in local_ids:
                    seg_region = tile_mask == lid
                    px_count   = int(seg_region.sum())
                    if px_count < min_px:
                        continue
                    if max_px is not None and px_count > max_px:
                        continue
                    global_id += 1
                    id_map[lid] = global_id

                # Apply remapped IDs to core region only
                core_tile = tile_mask[core_r0:core_r1, core_c0:core_c1]
                core_out  = np.zeros_like(core_tile, dtype=np.uint32)
                for lid, gid in id_map.items():
                    core_out[core_tile == lid] = gid

                # Write into output mask — zero values don't overwrite existing
                # (a field whose center is already written stays consistent)
                dst_r0 = row_start + core_r0
                dst_r1 = row_start + core_r1
                dst_c0 = col_start + core_c0
                dst_c1 = col_start + core_c1

                existing = out_mask[dst_r0:dst_r1, dst_c0:dst_c1]
                out_mask[dst_r0:dst_r1, dst_c0:dst_c1] = np.where(
                    core_out > 0,
                    core_out,
                    existing,   # keep what's already there if new is background
                )

        # Clean up temp files
        for p in [output_dir / "_tile_tmp.tif", output_dir / "_tile_mask_tmp.tif"]:
            if p.exists():
                p.unlink()

    print(f"Total unique segments after filtering: {global_id}")

    # Write full-resolution mask
    out_profile = profile.copy()
    out_profile.update(count=1, dtype="uint32", driver="GTiff", compress="lzw", nodata=0)
    with rasterio.open(mask_path, "w", **out_profile) as dst:
        dst.write(out_mask, 1)
    print(f"Mask saved → {mask_path}")

    # Vectorize
    print("Vectorizing mask ...")
    raster_to_vector(str(mask_path), str(vector_path))
    print(f"Vector saved → {vector_path}")

    return mask_path, vector_path