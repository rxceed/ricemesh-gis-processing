from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from argparse import ArgumentParser

def tile(
    source_tif: Path,
    output_dir: Path,
    tile_size: int,
) -> None:
    import cv2
    output_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(source_tif) as ref:
        H, W      = ref.height, ref.width
        profile   = ref.profile.copy()
        transform = ref.transform
        px_m      = abs(transform.a)       # metres per pixel (square pixels assumed)

    global_id   = 0

    col_starts  = list(range(0, W, tile_size))
    row_starts  = list(range(0, H, tile_size))
    total       = len(col_starts) * len(row_starts)
    done        = 0

    with rasterio.open(source_tif) as src:
        for row_off in row_starts:
            for col_off in col_starts:
                done += 1
                tmp_png     = output_dir / f"{source_tif.stem}/frame_{global_id}.png"
                tmp_png.parent.mkdir(parents=True, exist_ok=True)
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
                print(bands.shape, bands.dtype)
                # FastSAM expects a file path, not an in-memory array
                write = cv2.imwrite(
                    str(tmp_png),
                    cv2.cvtColor(bands, cv2.COLOR_RGB2BGR)  # OpenCV uses BGR order
                )
                if not write:
                    print(f"Error: Failed to write tile PNG at {tmp_png}")
                    continue
                global_id += 1

if __name__ == "__main__":
    arg_parser = ArgumentParser()
    arg_parser.add_argument("input", type=str, help="file path to input GeoTIFF relative to working directory")
    arg_parser.add_argument("output_dir", type=str, help="directory path for output tiles relative to working directory")
    arg_parser.add_argument("-t", "--tile-size", type=int, default=512, help="size of output tiles in pixels (default: 512)")
    args = arg_parser.parse_args()

    input_tif = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    tile_size  = args.tile_size

    tile(input_tif, output_dir, tile_size)