import os
from io import StringIO
from pathlib import Path
import math
import numpy as np
import requests
import torch
import rasterio
from rasterio.enums import Resampling
from omegaconf import OmegaConf, ListConfig, DictConfig
import opensr_model
import dotenv

dotenv.load_dotenv()

CONFIG_URL = os.getenv("LDSR2_CONFIG_URL")

def load_ldsr_model(device: str | None = None) -> tuple:
    if device is None:
        device = torch.accelerator.current_accelerator().type if torch.accelerator.is_available() else "cpu"
    print(f"Loading LDSR-S2 on {device}...")

    resp = requests.get(CONFIG_URL, timeout=30)
    resp.raise_for_status()
    config = OmegaConf.load(StringIO(resp.text))
    model = opensr_model.SRLatentDiffusion(config, device=device)
    model.load_pretrained(config.ckpt_version)
    model.eval()

    print("LDSR-S2 loaded.")
    return model, config, device

def resize_to_match_window(input_path: Path, lsdr_window: int = 128):
    with rasterio.open(input_path) as src:
        # Calculate target dimensions
        if lsdr_window:
            new_w, new_h = lsdr_window, lsdr_window
        else:
            # Logic for nearest power of 2: 2^round(log2(x))
            new_w = 2 ** round(math.log2(src.width))
            new_h = 2 ** round(math.log2(src.height))

        print(f"Resizing {src.width}x{src.height} to {new_w}x{new_h}...")

        # Choose resampling method based on upscaling vs downscaling
        resample_alg = Resampling.cubic if new_w > src.width else Resampling.lanczos

        # Read and resample data
        # data shape: (bands, new_h, new_w)
        data = src.read(
            out_shape=(src.count, new_h, new_w),
            resampling=resample_alg
        )

        # Update metadata (The transform must change to keep coordinates correct)
        transform = src.transform * src.transform.scale(
            (src.width / data.shape[-1]),
            (src.height / data.shape[-2])
        )

        profile = src.profile.copy()
        profile.update({
            'transform': transform,
            'width': new_w,
            'height': new_h,
            'nodata': src.nodata
        })

        output_path = input_path.parent / f"rescaled_{input_path.name}"
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(data)

    return output_path


def run_ldsr_on_geotiff(
    loaded_model_conf:tuple[opensr_model.SRLatentDiffusion, ListConfig, str],
    input_tif: Path,
    sampling_steps: int = 50,   # 50 is good tradeoff; 100 is max quality
) -> Path:
    import opensr_utils
    model, config, device = loaded_model_conf

    model_input_tif = resize_to_match_window(input_tif)
    with rasterio.open(model_input_tif) as src:
        is_single_window = (src.width == 128 and src.height == 128)

    print(f"Running SR: {input_tif.name}")
    sr_job = opensr_utils.large_file_processing(
        root=str(model_input_tif),
        model=model,
        window_size=(128, 128),
        factor=4,           # 10m → 2.5m
        overlap=6 if is_single_window else 12,
        eliminate_border_px=2,
        device=device,
        gpus=0,
    )
    sr_job.start_super_resolution()

    print(f"SR complete")
    return Path(model_input_tif.parent/"sr.tif")


def batch_sr(
    loaded_model_conf:tuple[opensr_model.SRLatentDiffusion, DictConfig|ListConfig, str],
    input_dir: Path,
    output_dir: Path,
    sampling_steps: int = 50,
    skip_existing: bool = True,
) -> list[Path]:
    """
    Apply SR to all GeoTIFFs in a directory.
    Loads the model once and reuses it across all tiles.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    tiles = sorted(input_dir.glob("*.tif"))
    results = []

    for tile in tiles:
        out = output_dir / tile.name
        if skip_existing and out.exists():
            results.append(out)
            continue
        try:
            run_ldsr_on_geotiff(tile, out, sampling_steps)
            results.append(out)
        except Exception as e:
            print(f"  FAILED {tile.name}: {e}")

    return results