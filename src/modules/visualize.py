# module_visualize.py

import numpy as np
import rasterio
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
from pathlib import Path
from rasterio.plot import reshape_as_image


def load_rgb_preview(sr_tif_path: Path, p_low: float = 2.0, p_high: float = 98.0) -> np.ndarray:
    """
    Load SR GeoTIFF and return a stretched uint8 RGB (H, W, 3).
    Uses true color [Red, Green, Blue] = [Band1, Band2, Band3].
    """
    with rasterio.open(sr_tif_path) as src:
        # Read only the first 3 bands (R, G, B) — skip NIR for true color display
        rgb = src.read([1, 2, 3]).astype(np.float32)   # (3, H, W)

    rgb_hwc = reshape_as_image(rgb)                     # (H, W, 3)
    out = np.zeros_like(rgb_hwc, dtype=np.float32)
    for i in range(3):
        lo = np.percentile(rgb_hwc[..., i], p_low)
        hi = np.percentile(rgb_hwc[..., i], p_high)
        out[..., i] = np.clip((rgb_hwc[..., i] - lo) / (hi - lo + 1e-8), 0.0, 1.0)

    return (out * 255).astype(np.uint8)


def rasterize_vector_masks(
    vector_path: Path,
    reference_tif: Path,
) -> tuple[np.ndarray, gpd.GeoDataFrame]:
    """
    Burn vector polygons into a raster aligned to reference_tif.
    Each polygon gets a unique integer ID.
    Returns:
        label_raster : (H, W) int32 — 0 = no segment, 1..N = segment IDs
        gdf          : the GeoDataFrame (reprojected to raster CRS)
    """
    from rasterio.features import rasterize as rio_rasterize
    from rasterio.transform import from_bounds

    with rasterio.open(reference_tif) as src:
        out_shape = (src.height, src.width)
        transform = src.transform
        crs = src.crs

    gdf = gpd.read_file(vector_path).to_crs(crs)

    # Pair each geometry with a unique int ID starting from 1
    shapes = [
        (geom, idx + 1)
        for idx, geom in enumerate(gdf.geometry)
        if geom is not None and geom.is_valid
    ]

    label_raster = rio_rasterize(
        shapes,
        out_shape=out_shape,
        transform=transform,
        fill=0,
        dtype=np.int32,
    )
    return label_raster, gdf


def overlay_masks_on_image(
    sr_tif_path: Path,
    vector_path: Path,           # GeoJSON or GPKG from SAM2 / filter step
    output_png_path: Path,
    alpha: float = 0.35,         # mask fill opacity — 0=invisible, 1=opaque
    edge_color: str = "yellow",  # polygon outline color
    edge_width: float = 0.6,
    figsize: tuple = (14, 14),
    dpi: int = 150,
    title: str = "SAM2 segmentation overlay",
    max_segments_legend: int = 0,  # 0 = don't show legend (too many segments)
) -> None:
    """
    Overlay SAM2 segment polygons on the true-color SR image and save as PNG.

    Strategy:
    - True color background from SR bands 1/2/3 (R/G/B)
    - Each segment filled with a distinct random color at low opacity
    - Polygon outlines drawn on top in a high-contrast color
    - Works with both the raw SAM2 output (all segments) and the filtered
    farm plot output — just pass whichever vector you want to preview

    alpha=0.35 is a good default:
    high enough to see the segments, low enough to see the image beneath.
    Raise to 0.5 if segments are hard to see, lower to 0.2 for subtle overlay.
    """
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading SR image: {sr_tif_path.name}")
    rgb = load_rgb_preview(sr_tif_path)
    H, W = rgb.shape[:2]

    print(f"Rasterizing {vector_path.name} ...")
    label_raster, gdf = rasterize_vector_masks(vector_path, sr_tif_path)
    n_segments = int(label_raster.max())
    print(f"  Segments to render: {n_segments}")

    # Build a per-segment color LUT using a qualitative colormap.
    # We seed the RNG so colors are consistent across runs for the same tile.
    rng = np.random.default_rng(seed=42)
    # Shape: (N+1, 4) RGBA — index 0 = background (transparent)
    colors_rgba = np.zeros((n_segments + 1, 4), dtype=np.float32)
    colors_rgba[1:, :3] = rng.uniform(0.2, 0.95, size=(n_segments, 3))
    colors_rgba[1:, 3] = alpha

    # Build colored mask overlay: (H, W, 4) RGBA
    overlay = colors_rgba[label_raster]   # fancy indexing — very fast

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi)
    ax.imshow(rgb)
    ax.imshow(overlay, interpolation="none")

    # Draw polygon outlines on top for sharp boundaries
    # We use gdf.boundary for clean edges without fill (fill is already done above)
    with rasterio.open(sr_tif_path) as src:
        bounds = src.bounds
        pixel_width  = (bounds.right - bounds.left)  / W
        pixel_height = (bounds.top   - bounds.bottom) / H

    # Convert geographic coordinates to pixel coordinates for matplotlib
    def geo_to_pixel(x, y):
        col = (x - bounds.left)   / pixel_width
        row = (bounds.top  - y)   / pixel_height
        return col, row

    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        # Handle both Polygon and MultiPolygon
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            xs, ys = poly.exterior.xy
            px, py = geo_to_pixel(np.array(xs), np.array(ys))
            ax.plot(px, py, color=edge_color, linewidth=edge_width, alpha=0.9)
            # Interior rings (holes) — rare for farm plots but handle anyway
            for interior in poly.interiors:
                xs_i, ys_i = interior.xy
                px_i, py_i = geo_to_pixel(np.array(xs_i), np.array(ys_i))
                ax.plot(px_i, py_i, color=edge_color, linewidth=edge_width * 0.7, alpha=0.7)

    ax.set_title(f"{title}\n{n_segments} segments | {vector_path.name}", fontsize=11)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_png_path, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Saved overlay → {output_png_path}")


def overlay_comparison(
    sr_tif_path: Path,
    raw_segments_path: Path,      # all SAM2 segments (before NDVI filter)
    filtered_plots_path: Path,    # farm plots only (after NDVI filter)
    output_png_path: Path,
    alpha: float = 0.35,
    figsize: tuple = (20, 10),
    dpi: int = 150,
) -> None:
    """
    Side-by-side: raw SAM2 output (left) vs filtered farm plots (right).
    Useful for evaluating how well the NDVI filter is working.
    """
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    rgb = load_rgb_preview(sr_tif_path)
    H, W = rgb.shape[:2]

    def build_overlay(vector_path):
        label_raster, gdf = rasterize_vector_masks(vector_path, sr_tif_path)
        n = int(label_raster.max())
        rng = np.random.default_rng(seed=42)
        colors = np.zeros((n + 1, 4), dtype=np.float32)
        colors[1:, :3] = rng.uniform(0.2, 0.95, size=(n, 3))
        colors[1:, 3] = alpha
        return colors[label_raster], gdf, n

    raw_overlay,      gdf_raw,      n_raw      = build_overlay(raw_segments_path)
    filtered_overlay, gdf_filtered, n_filtered = build_overlay(filtered_plots_path)

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=figsize, dpi=dpi)

    for ax, overlay, gdf, n, label in [
        (ax_left,  raw_overlay,      gdf_raw,      n_raw,      "Raw SAM2"),
        (ax_right, filtered_overlay, gdf_filtered, n_filtered, "Farm plots (NDVI filtered)"),
    ]:
        ax.imshow(rgb)
        ax.imshow(overlay, interpolation="none")
        ax.set_title(f"{label}\n{n} segments", fontsize=11)
        ax.axis("off")

    plt.suptitle(sr_tif_path.stem, fontsize=13, y=1.01)
    plt.tight_layout()
    plt.savefig(output_png_path, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Saved comparison → {output_png_path}")

from pathlib import Path





if __name__ == "__main__":
    OUT_DIR = Path.joinpath(Path.cwd(), "segmented_output").resolve()
    GEE_OUTPUT = Path.joinpath(Path.cwd(), "gee_output").resolve()
    # Preview just the farm plots on true color
    overlay_masks_on_image(
    sr_tif_path     = GEE_OUTPUT/"sr.tif",
    vector_path     = OUT_DIR / "sam2_vector.json",
    output_png_path = OUT_DIR / "preview_filtered.png",
    alpha=0.35,
    edge_color="yellow",
    title="Farm plot segmentation - True color",
    )

    overlay_masks_on_image(
    sr_tif_path     = OUT_DIR/"sam2_prep_ndvi.tif",
    vector_path     = OUT_DIR / "sam2_vector.json",
    output_png_path = OUT_DIR / "preview_prep.png",
    alpha=0.35,
    edge_color="yellow",
    title="Farm plot segmentation - NDVI",
    )

    # Side-by-side raw vs filtered — useful for tuning the NDVI threshold
    overlay_comparison(
        sr_tif_path          = GEE_OUTPUT/"sr.tif",
        raw_segments_path    = OUT_DIR/"sam2_vector.json",
        filtered_plots_path  = OUT_DIR / "filtered_plot.gpkg",
        output_png_path      = OUT_DIR / "filtered_comparison.png",
    )