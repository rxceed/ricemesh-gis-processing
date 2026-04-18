import numpy as np
import rasterio
from pathlib import Path
import os, sys

DSEN2_ROOT_DIR = Path.joinpath(Path.cwd(), "DSen2").resolve()
DSEN2_TESTING_DIR = Path(DSEN2_ROOT_DIR/"testing")
DSEN2_UTILS_DIR = Path(DSEN2_ROOT_DIR/"utils")

def _validate_dsen2_layout():
    """
    Hard-fail early with a clear message if anything is missing.
    Much better than getting a cryptic ImportError later.THIS_FILE_DIR  = Path(__file__).resolve().parent
    """
    required = {
        "DSen2 root":       DSEN2_ROOT_DIR,
        "testing dir":      DSEN2_TESTING_DIR,
        "supres.py":        DSEN2_TESTING_DIR / "supres.py",
        "utils dir":        DSEN2_ROOT_DIR / "utils",
        "DSen2Net.py":      DSEN2_ROOT_DIR / "utils" / "DSen2Net.py",
        "patches.py":       DSEN2_ROOT_DIR / "utils" / "patches.py",
        "models dir":       DSEN2_ROOT_DIR / "models",
    }
    missing = [f"  {label}: {path}" for label, path in required.items()
            if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "DSen2 installation incomplete. Missing:\n"
            + "\n".join(missing)
            + f"\n\nExpected DSen2 to be cloned at:\n  {DSEN2_ROOT_DIR}"
        )

def _setup_dsen2_paths():
    """
    Insert DSen2 paths into sys.path so imports resolve correctly.
    Safe to call multiple times — checks before inserting.
    """
    # DSen2/testing/ must be on path so `import supres` finds supres.py
    if str(DSEN2_TESTING_DIR) not in sys.path:
        sys.path.insert(0, str(DSEN2_TESTING_DIR))

    # DSen2/ root must be on path so `from utils.DSen2Net import s2model`
    # inside supres.py finds the utils/ package
    if str(DSEN2_ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(DSEN2_ROOT_DIR))

def _import_dsen2():
    _validate_dsen2_layout()
    _setup_dsen2_paths()
    original_cwd = os.getcwd()
    
    # --- THE FIX: CACHE SWAPPING ---
    # 1. Store your existing 'utils' if it's already loaded
    temp_utils = sys.modules.get('utils')
    
    # 2. Temporarily remove it from the cache so Python is 
    # forced to look at sys.path (where DSen2 is now #0)
    if 'utils' in sys.modules:
        del sys.modules['utils']

    try:
        os.chdir(DSEN2_TESTING_DIR)
        
        # 3. This will now find DSen2/utils/ instead of your src/utils/
        import supres
        # We also need to make sure the submodules are cached correctly 
        # so they don't get mixed up later.
        return supres.DSen2_20
        
    finally:
        os.chdir(original_cwd)
        
        # 4. Restore your original 'utils' to the cache so your 
        # other project code continues to work normally.
        if temp_utils:
            sys.modules['utils'] = temp_utils

DSen2_20 = _import_dsen2()
S2_BANDS_10M = ["B2", "B3", "B4", "B8"]
S2_BANDS_20M = ["B5", "B6", "B7", "B8A", "B11", "B12"]
DEFAULT_BAND_INDEX_MAP = {"B2": 1, "B3": 2, "B4": 3, "B8": 4,
                        "B5": 5, "B6": 6, "B7": 7, "B8A": 8, "B11": 9, "B12": 10}

def apply_dsen2_to_geotiff(
    input_tif_path: Path,       # GeoTIFF with all S2 bands (10m + 20m)
    output_tif_path: Path,
    band_index_map: dict = DEFAULT_BAND_INDEX_MAP,       # maps band name → 1-indexed rasterio band number
    deep: bool = False,
) -> Path:
    """
    Run DSen2_20 on a multi-band GeoTIFF downloaded from GEE.
    No XML, no SAFE directory, no subprocess.

    band_index_map example (matches the GEE download from module_01):
        {
        "B2": 1, "B3": 2, "B4": 3, "B8": 4,   # 10m bands
        "B5": 5, "B6": 6, "B7": 7,              # 20m bands
        "B8A": 8, "B11": 9, "B12": 10,
        }

    Why HWC format for DSen2 inputs?
    DSen2 was originally written for TensorFlow's NHWC convention.
    Even though the repo has some CHW transposes internally, DSen2_20
    expects (H, W, C) input arrays. Rasterio gives (C, H, W) — we
    transpose before passing, then transpose back.
    """
    output_tif_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(input_tif_path) as src:
        profile = src.profile
        full_transform = src.transform
        crs = src.crs

        # Read 10m bands → (4, H, W) → transpose → (H, W, 4)
        d10_chw = np.stack(
            [src.read(band_index_map[b]).astype(np.float32)
            for b in S2_BANDS_10M],
            axis=0,
        )
        d10 = d10_chw.transpose(1, 2, 0)   # (H, W, 4)

        # Read 20m bands.
        # GEE downloads all bands at the requested scale (e.g. 10m),
        # meaning the 20m bands are already upsampled to 10m pixels.
        # DSen2 needs the NATIVE 20m resolution — half the pixel count.
        # We downsample back to native before passing to DSen2.
        d20_10m = np.stack(
            [src.read(band_index_map[b]).astype(np.float32)
            for b in S2_BANDS_20M],
            axis=0,
        )   # shape: (6, H, W) — upsampled by GEE

        H, W = d10.shape[:2]
        # Downsample each 20m band to (H/2, W/2) using area averaging.
        # Why INTER_AREA and not INTER_LINEAR?
        # INTER_AREA computes the true pixel average — physically equivalent
        # to what a 20m sensor would read. Other methods introduce aliasing.
        import cv2
        d20_channels = []
        for c in range(d20_10m.shape[0]):
            band_native = cv2.resize(
                d20_10m[c],
                (W // 2, H // 2),
                interpolation=cv2.INTER_AREA,
            )
            d20_channels.append(band_native)
        d20 = np.stack(d20_channels, axis=-1)   # (H/2, W/2, 6)

    # ── Pad Arrays for DSen2 ─────────────────────────────────────────────────
    # DSen2 has a hardcoded patch size of 128 for 10m bands (64 for 20m bands).
    # If the image is smaller than this, it crashes. We pad the image to at least 128,
    # ensuring the dimensions remain even numbers so the 10m/20m ratio perfectly matches.
    target_H = max(128, H + (H % 2))
    target_W = max(128, W + (W % 2))

    pad_h = target_H - H
    pad_w = target_W - W

    # Pad using 'reflect' to prevent harsh black borders that cause artifacts in CNNs
    d10_padded = np.pad(d10, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')

    h20, w20 = d20.shape[:2]
    pad_h20 = (target_H // 2) - h20
    pad_w20 = (target_W // 2) - w20

    d20_padded = np.pad(d20, ((0, pad_h20), (0, pad_w20), (0, 0)), mode='reflect')

    # ── Run DSen2 ────────────────────────────────────────────────────────────
    print(
        f"Running DSen2_20 on {input_tif_path.name} " 
        f"[d10_padded={d10_padded.shape}, d20_padded={d20_padded.shape}] ..."
    )
    import os
    original_dir = os.getcwd()
    try:
        os.chdir(DSEN2_TESTING_DIR)   # model weight relative paths need this
        # Run inference on the padded arrays
        sr_output_padded = DSen2_20(d10_padded, d20_padded, deep=deep)
        
        # Crop the super-resolved output back to the original image dimensions
        sr_output = sr_output_padded[:H, :W, :]
        
    finally:
        os.chdir(original_dir)

    # ── Assemble output: 10m bands + SR 20m bands ────────────────────────────
    # Concatenate original 10m bands with SR output along channel axis
    # Result: (H, W, 10) — [B2,B3,B4,B8] + SR[B5,B6,B7,B8A,B11,B12]
    full_output_hwc = np.concatenate(
        [d10, sr_output.astype(np.float32)],
        axis=-1,
    )
    full_output_chw = full_output_hwc.transpose(2, 0, 1)   # (10, H, W)

    # ── Save with original georeferencing ────────────────────────────────────
    out_profile = profile.copy()
    out_profile.update(
        count=full_output_chw.shape[0],
        dtype=np.float32,
        driver="GTiff",
        compress="lzw",     # lossless compression — important for training data
    )

    with rasterio.open(output_tif_path, "w", **out_profile) as dst:
        dst.write(full_output_chw)
        # Tag bands so downstream code knows what's what
        for i, name in enumerate(S2_BANDS_10M + S2_BANDS_20M, start=1):
            dst.update_tags(i, band_name=name, resolution="10m_sr")

    print(f"Saved SR tile: {output_tif_path}")
    return output_tif_path
