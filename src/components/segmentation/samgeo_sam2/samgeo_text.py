# module_drone_segment_grounded.py

from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from samgeo.text_sam import LangSAM
from samgeo.common import raster_to_vector


def load_grounded_sam(device: str | None = None) -> LangSAM:
    """
    LangSAM = Grounding DINO + SAM2, wrapped by samgeo.
    No HuggingFace access needed. Downloads weights automatically on first run.

    Why this over plain SamGeo2 automatic?
    Automatic mode has no concept of "rice field" — it segments everything
    with equal priority. LangSAM only segments what you ask for.
    A field partially obscured by shadow still gets found because the
    detector reasons about the whole image context, not just local pixels.
    """
    import torch
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Grounded SAM on {device} ...")
    return LangSAM(model_type="sam2-hiera-large")   # uses SAM2 as the mask backend


def read_tile_rgb(
    src: rasterio.DatasetReader,
    window: Window,
) -> np.ndarray:
    """Read window as (H, W, 3) uint8."""
    data = np.stack(
        [src.read(i + 1, window=window).astype(np.float32)
        for i in range(min(3, src.count))],
        axis=-1,
    )
    for c in range(data.shape[2]):
        lo, hi = np.percentile(data[..., c], [2, 98])
        data[..., c] = np.clip((data[..., c] - lo) / (hi - lo + 1e-8), 0, 1)
    return (data * 255).astype(np.uint8)


def segment_orthophoto_samtext(
    orthophoto_path: Path,
    output_dir: Path,
    text_prompt: str = "rice paddy field",
    box_threshold: float = 0.25,   # Grounding DINO detection confidence
    text_threshold: float = 0.25,  # text-image similarity threshold
    tile_size: int = 1024,
    overlap: int = 128,
    min_area_m2: float = 100.0,
) -> tuple[Path, Path]:
    """
    Segment farm plots using text-prompted Grounded SAM.

    Prompt tips for rice paddy in East Java:
    - "rice paddy field"        — most reliable
    - "agricultural field"      — catches non-rice crops too (wider)
    - "paddy field, crop field" — comma-separated = logical OR in Grounding DINO
    - "flooded field"           — useful during transplanting season

    box_threshold=0.25 is permissive — Grounding DINO will propose more
    bounding boxes, SAM2 then decides the exact mask boundary.
    Raise to 0.35 if you're getting too many false positives (roads, ponds).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem        = orthophoto_path.stem
    mask_path   = output_dir / f"{stem}_mask.tif"
    vector_path = output_dir / f"{stem}_segments.geojson"

    model = load_grounded_sam()

    with rasterio.open(orthophoto_path) as src:
        H, W      = src.height, src.width
        profile   = src.profile.copy()
        crs       = src.crs
        transform = src.transform
        px_size   = abs(transform.a)
        min_px    = max(1, int(min_area_m2 / (px_size ** 2)))

    out_mask   = np.zeros((H, W), dtype=np.uint32)
    global_id  = 0
    stride     = tile_size - overlap

    col_starts = list(range(0, W, stride))
    row_starts = list(range(0, H, stride))
    total      = len(col_starts) * len(row_starts)
    done       = 0

    for row_off in row_starts:
        for col_off in col_starts:
            done += 1
            col_end   = min(col_off + tile_size, W)
            row_end   = min(row_off + tile_size, H)
            col_start = max(0, col_end - tile_size)
            row_start = max(0, row_end - tile_size)
            actual_w  = col_end - col_start
            actual_h  = row_end - row_start

            print(f"  Tile {done}/{total}  col={col_start}–{col_end}  row={row_start}–{row_end}")

            with rasterio.open(orthophoto_path) as src:
                win      = Window(col_start, row_start, actual_w, actual_h)
                tile_rgb = read_tile_rgb(src, win)
                t_tfm    = src.window_transform(win)

            # Save tile for LangSAM (needs a file path)
            tmp = output_dir / "_tile_tmp.tif"
            with rasterio.open(tmp, "w", driver="GTiff", count=3,
                            dtype=np.uint8, height=actual_h, width=actual_w,
                            crs=crs, transform=t_tfm) as tmp_dst:
                tmp_dst.write(tile_rgb.transpose(2, 0, 1))
            try:
                # LangSAM predict: returns masks, boxes, phrases, logits
                prediction = model.predict(
                    image=str(tmp),
                    text_prompt=text_prompt,
                    box_threshold=box_threshold,
                    text_threshold=text_threshold,
                    output=None,    # don't auto-save, we handle it
                )
                if prediction is None:
                    print(f"    No objects matching '{text_prompt}' found in this tile.")
                    continue

                # 4. Safely unpack now that we know it's not None
                masks, boxes, phrases, logits = prediction

                if masks is None or len(masks) == 0:
                    continue

                # masks is (N, H, W) bool numpy
                for mask_bool in masks:
                    px_count = int(mask_bool.sum())
                    if px_count < min_px:
                        continue
                    global_id += 1
                    dst_r = slice(row_start, row_start + actual_h)
                    dst_c = slice(col_start, col_start + actual_w)
                    existing = out_mask[dst_r, dst_c]
                    out_mask[dst_r, dst_c] = np.where(
                        (mask_bool > 0) & (existing == 0),
                        global_id,
                        existing,
                    )

            except Exception as e:
                print(f"    Failed: {e}")

    if tmp.exists():
        tmp.unlink()

    out_profile = profile.copy()
    out_profile.update(count=1, dtype="uint32", compress="lzw", nodata=0)
    with rasterio.open(mask_path, "w", **out_profile) as dst:
        dst.write(out_mask, 1)

    raster_to_vector(str(mask_path), str(vector_path))
    print(f"Done. {global_id} segments → {vector_path}")
    return mask_path, vector_path