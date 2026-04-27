"""
vari_prep.py

VARI (Visible Atmospherically Resistant Index) computation and visualization
for RGB-only drone orthophotos.

Why VARI instead of NDVI for drone imagery
──────────────────────────────────────────
Drone cameras capture only R, G, B — no NIR band.
VARI = (G - R) / (G + R - B) uses only what is available.
It was designed to be resistant to atmospheric effects without requiring
atmospheric correction, which drone orthophotos rarely receive.

Typical VARI values for East Java paddy
  Active rice (vegetative)  : 0.15 – 0.50
  Bare soil / bunds         : -0.05 – 0.10
  Roads / concrete          : -0.15 – 0.05
  Irrigation water / shadow : < -0.10

Edge cases handled
  Denominator (G+R-B) ≈ 0   → neutral-gray pixels (concrete, rooftops).
                               VARI is undefined here. We set NaN so they
                               are excluded from statistics without skewing
                               the distribution.
  White / black nodata border → masked as NaN before any computation.
"""

from pathlib import Path
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize


def _build_nodata_mask(
    bands: np.ndarray,              # (C, H, W) — any integer or float dtype
    white_fraction: float = 0.98,   # fraction of dtype max considered "white"
    black_fraction: float = 0.02,
) -> np.ndarray:                    # (H, W) bool — True = nodata
    """
    Detect white-border and black-border nodata pixels from orthophoto stitching.

    We check ALL bands simultaneously. A single bright band (e.g. a white roof)
    is not flagged — only pixels where every band is simultaneously at the limit.
    """
    if np.issubdtype(bands.dtype, np.integer):
        max_val = float(np.iinfo(bands.dtype).max)
    else:
        max_val = float(bands.max()) or 1.0

    is_white = np.all(bands > white_fraction * max_val, axis=0)
    is_black = np.all(bands < black_fraction * max_val, axis=0)
    return is_white | is_black


def compute_vari_from_bands(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    epsilon_fraction: float = 0.02,
) -> np.ndarray:
    """
    Compute VARI from three same-shape band arrays.

    Parameters
    ----------
    red, green, blue    : Any numeric dtype — cast to float32 internally.
    epsilon_fraction    : Stability guard as a fraction of the green channel
                          dynamic range. Pixels where |G+R-B| < epsilon are
                          set to NaN (unstable denominator — neutral-gray pixels).
                          0.02 ≈ 5 DN for uint8, ≈ 200 DN for uint16.

    Returns
    -------
    np.ndarray  float32 (H, W), clipped to [-1.0, 1.0].
                NaN for unstable pixels. Does NOT mask nodata — the caller
                applies the nodata mask after getting the raw VARI array.
    """
    r = red.astype(np.float32)
    g = green.astype(np.float32)
    b = blue.astype(np.float32)

    denom   = g + r - b
    epsilon = epsilon_fraction * float(g.max() or 1.0)

    stable  = np.abs(denom) >= epsilon
    vari    = np.full_like(r, np.nan)
    vari[stable] = (g[stable] - r[stable]) / denom[stable]
    vari    = np.clip(vari, -1.0, 1.0)
    return vari


def vari_to_uint8_rgb(
    vari: np.ndarray,
    vmin: float = -0.15,
    vmax: float = 0.55,
    colormap: str = "RdYlGn",
    nodata_color: tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    """
    Colorize a VARI float32 array into a (H, W, 3) uint8 RGB image for SAM input.

    Color semantics (RdYlGn):
      vmax = 0.55  → saturated green   (peak rice canopy — strong plot signal)
      ~ 0.2        → yellow-green      (moderate vegetation)
      ~ 0.0        → yellow            (soil, bunds — boundary marker)
      vmin = -0.15 → red               (water channels, deep shadow)

    Why these bounds?
      East Java paddy at vegetative peak peaks at VARI ≈ 0.50.
      vmax = 0.55 ensures peak pixels map to full green saturation, maximising
      contrast against bund pixels (VARI ≈ 0.05, yellow-green).
      vmin = -0.15 captures irrigation channels without mapping normal roads
      (VARI ≈ -0.05) to the extreme red, which would exaggerate road edges.

    NaN pixels → nodata_color (white).
    White blends with the orthophoto background so FastSAM doesn't generate
    spurious boundary segments at the image edge.
    """
    cmap = plt.get_cmap(colormap)
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)

    nan_mask  = np.isnan(vari)
    vari_fill = np.where(nan_mask, 0.0, vari)   # placeholder, overwritten below

    rgba = cmap(norm(vari_fill))                 # (H, W, 4) float [0, 1]
    rgb  = (rgba[..., :3] * 255).astype(np.uint8)
    rgb[nan_mask] = nodata_color
    return rgb


def preprocess_vari_geotiff(
    input_tif: Path,
    output_tif: Path,
    band_indices: dict[str, int] | None = None,
) -> tuple[Path, np.ndarray]:
    """
    Read an RGB GeoTIFF → compute VARI → colorize → write a 3-band uint8 GeoTIFF.

    The output GeoTIFF carries the exact CRS and affine transform of the input so
    downstream georeferenced operations (mask warping, vectorization) remain valid.

    Parameters
    ----------
    input_tif     : RGB drone orthophoto as GeoTIFF.
    output_tif    : Destination path. Parent dirs are created if absent.
    band_indices  : 0-indexed band positions for R, G, B.
                    Default {"red": 0, "green": 1, "blue": 2}.

    Returns
    -------
    output_tif    : Same Path passed in — useful for chaining.
    vari_array    : Raw float32 VARI (H, W) with NaN for masked pixels.
                    Returned so the caller can reuse it in the filter step
                    without re-reading the TIF.
    """
    if band_indices is None:
        band_indices = {"red": 0, "green": 1, "blue": 2}

    with rasterio.open(input_tif) as src:
        # rasterio uses 1-indexed bands
        red       = src.read(band_indices["red"]   + 1)
        green     = src.read(band_indices["green"] + 1)
        blue      = src.read(band_indices["blue"]  + 1)
        all_bands = src.read()           # (C, H, W) for nodata detection
        profile   = src.profile.copy()

    nodata_mask = _build_nodata_mask(all_bands)
    vari        = compute_vari_from_bands(red, green, blue)
    vari[nodata_mask] = np.nan           # mask stitching border

    rgb_uint8   = vari_to_uint8_rgb(vari)

    out_profile = profile.copy()
    out_profile.update(count=3, dtype=np.uint8, nodata=None)

    output_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_tif, "w", **out_profile) as dst:
        dst.write(rgb_uint8.transpose(2, 0, 1))   # (H,W,3) → (3,H,W)

    print(
        f"VARI GeoTIFF → {output_tif}\n"
        f"  VARI range : [{np.nanmin(vari):.3f}, {np.nanmax(vari):.3f}]  "
        f"mean={np.nanmean(vari):.3f}\n"
        f"  Nodata px  : {nodata_mask.sum():,} ({100 * nodata_mask.mean():.1f}%)"
    )
    return output_tif, vari