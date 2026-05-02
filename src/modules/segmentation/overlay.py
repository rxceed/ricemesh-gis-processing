from pathlib import Path
import numpy as np
import rasterio
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from rasterio.plot import reshape_as_image


def load_rgb_uint8(tif_path: Path, p_low: float = 2.0, p_high: float = 98.0) -> tuple[np.ndarray, dict]:
    """Load first 3 bands of a GeoTIFF as a display-ready uint8 (H,W,3)."""
    with rasterio.open(tif_path) as src:
        n_bands = min(3, src.count)
        rgb_chw = np.stack(
            [src.read(i + 1).astype(np.float32) for i in range(n_bands)],
            axis=0,
        )
        profile = src.profile
        bounds  = src.bounds

    rgb_hwc = reshape_as_image(rgb_chw)
    out     = np.zeros_like(rgb_hwc, dtype=np.float32)
    for i in range(rgb_hwc.shape[2]):
        lo = np.percentile(rgb_hwc[..., i], p_low)
        hi = np.percentile(rgb_hwc[..., i], p_high)
        out[..., i] = np.clip((rgb_hwc[..., i] - lo) / (hi - lo + 1e-8), 0, 1)

    return (out * 255).astype(np.uint8), profile, bounds


def overlay_segments_on_orthophoto(
    orthophoto_path: Path,
    segments_geojson: Path,      # full polygon masks from SAM3
    output_png: Path,
    alpha_fill: float = 0.25,
    edge_color: str = "cyan",
    edge_width: float = 0.8,
    figsize: tuple = (16, 16),
    dpi: int = 150,
    title: str = "Farm plot segmentation",
) -> None:
    """Overlay full segment polygons on the orthophoto."""
    output_png.parent.mkdir(parents=True, exist_ok=True)

    rgb, profile, bounds = load_rgb_uint8(orthophoto_path)
    H, W = rgb.shape[:2]

    gdf = gpd.read_file(segments_geojson)
    if gdf.crs and gdf.crs != profile["crs"]:
        gdf = gdf.to_crs(profile["crs"])

    px_w = (bounds.right - bounds.left) / W
    px_h = (bounds.top   - bounds.bottom) / H

    def geo_to_px(x, y):
        return (x - bounds.left) / px_w, (bounds.top - y) / px_h

    rng = np.random.default_rng(42)
    n   = len(gdf)
    colors = rng.uniform(0.2, 0.9, size=(n, 3))

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi)
    ax.imshow(rgb)

    for i, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        color = colors[i % n]
        for poly in polys:
            xs, ys = poly.exterior.xy
            px, py = geo_to_px(np.array(xs), np.array(ys))
            # Filled polygon at low opacity
            ax.fill(px, py, color=color, alpha=alpha_fill)
            # Sharp edge on top
            ax.plot(px, py, color=edge_color, linewidth=edge_width, alpha=0.9)

    ax.set_title(f"{title}\n{n} segments | {orthophoto_path.name}", fontsize=11)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_png, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Overlay saved → {output_png}")


def overlay_bboxes_on_orthophoto(
    orthophoto_path: Path,
    bbox_geojson: Path,          # bounding box polygons from export_bboxes()
    output_png: Path,
    edge_color: str = "lime",
    fill_color: str = "lime",
    fill_alpha: float = 0.08,
    edge_width: float = 1.2,
    show_labels: bool = True,    # show plot_id inside each bbox
    figsize: tuple = (16, 16),
    dpi: int = 150,
    title: str = "Farm plot bounding boxes",
) -> None:
    """
    Overlay bounding box rectangles on the orthophoto.
    Labels show plot_id so you can cross-reference with the GeoJSON.
    """
    output_png.parent.mkdir(parents=True, exist_ok=True)

    rgb, profile, bounds = load_rgb_uint8(orthophoto_path)
    H, W = rgb.shape[:2]

    gdf = gpd.read_file(bbox_geojson)
    # Bounding box GeoJSON is in WGS84 — reproject to raster CRS
    if gdf.crs and str(gdf.crs) != str(profile["crs"]):
        gdf = gdf.to_crs(profile["crs"])

    px_w = (bounds.right - bounds.left) / W
    px_h = (bounds.top   - bounds.bottom) / H

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi)
    ax.imshow(rgb)

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        minx, miny, maxx, maxy = geom.bounds
        # Convert geographic corners to pixel coordinates
        px_x0 = (minx - bounds.left) / px_w
        px_y0 = (bounds.top - maxy)   / px_h
        px_w_  = (maxx - minx) / px_w
        px_h_  = (maxy - miny) / px_h

        rect = mpatches.Rectangle(
            (px_x0, px_y0), px_w_, px_h_,
            linewidth=edge_width,
            edgecolor=edge_color,
            facecolor=fill_color,
            alpha=fill_alpha,
        )
        ax.add_patch(rect)

        if show_labels:
            cx = px_x0 + px_w_ / 2
            cy = px_y0 + px_h_ / 2
            area_ha = row.get("area_ha", "")
            label   = f"{row.get('plot_id', '')} ({area_ha:.2f}ha)" if area_ha else str(row.get("plot_id", ""))
            ax.text(
                cx, cy, label,
                ha="center", va="center",
                fontsize=6, color="white",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.1", fc="black", alpha=0.45, ec="none"),
            )

    ax.set_title(f"{title}\n{len(gdf)} plots | {orthophoto_path.name}", fontsize=11)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_png, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"BBox overlay saved → {output_png}")


def overlay_comparison(
    orthophoto_path: Path,
    segments_geojson: Path,
    bbox_geojson: Path,
    output_png: Path,
    figsize: tuple = (24, 12),
    dpi: int = 150,
) -> None:
    """Side-by-side: full polygons (left) vs bounding boxes (right)."""
    output_png.parent.mkdir(parents=True, exist_ok=True)

    rgb, profile, bounds = load_rgb_uint8(orthophoto_path)
    H, W = rgb.shape[:2]
    px_w = (bounds.right - bounds.left) / W
    px_h = (bounds.top   - bounds.bottom) / H

    def geo_to_px(x, y):
        return (x - bounds.left) / px_w, (bounds.top - y) / px_h

    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=figsize, dpi=dpi)

    # LEFT — full polygon masks
    gdf_seg = gpd.read_file(segments_geojson)
    if gdf_seg.crs and str(gdf_seg.crs) != str(profile["crs"]):
        gdf_seg = gdf_seg.to_crs(profile["crs"])

    ax_l.imshow(rgb)
    rng = np.random.default_rng(42)
    colors = rng.uniform(0.2, 0.9, size=(len(gdf_seg), 3))
    for i, (_, row) in enumerate(gdf_seg.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        for poly in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom]):
            xs, ys = poly.exterior.xy
            px, py = geo_to_px(np.array(xs), np.array(ys))
            ax_l.fill(px, py, color=colors[i % len(gdf_seg)], alpha=0.25)
            ax_l.plot(px, py, color="cyan", linewidth=0.6, alpha=0.9)
    ax_l.set_title(f"SAM3 segments ({len(gdf_seg)})", fontsize=11)
    ax_l.axis("off")

    # RIGHT — bounding boxes
    gdf_bb = gpd.read_file(bbox_geojson)
    if gdf_bb.crs and str(gdf_bb.crs) != str(profile["crs"]):
        gdf_bb = gdf_bb.to_crs(profile["crs"])

    ax_r.imshow(rgb)
    for _, row in gdf_bb.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        minx, miny, maxx, maxy = geom.bounds
        px_x0 = (minx - bounds.left) / px_w
        px_y0 = (bounds.top - maxy)   / px_h
        pw    = (maxx - minx) / px_w
        ph    = (maxy - miny) / px_h
        ax_r.add_patch(mpatches.Rectangle(
            (px_x0, px_y0), pw, ph,
            linewidth=1.0, edgecolor="yellow",
            facecolor="yellow", alpha=0.08,
        ))
    ax_r.set_title(f"Bounding boxes ({len(gdf_bb)})", fontsize=11)
    ax_r.axis("off")

    plt.suptitle(orthophoto_path.stem, fontsize=13, y=1.01)
    plt.tight_layout()
    plt.savefig(output_png, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Comparison saved → {output_png}")

# --- CORE HELPER FUNCTION ---
# (Keep this in your module so the 3 functions below can share it)

def _add_bboxes_to_ax(
    ax: plt.Axes,
    geojson_path: Path,
    bounds, 
    px_w: float, 
    px_h: float, 
    profile_crs, 
    edge_c: str, 
    fill_c: str, 
    fill_alpha: float, 
    edge_width: float, 
    label_prefix: str
) -> int:
    """Helper to read a GeoJSON and draw bounding boxes onto an existing matplotlib Axis."""
    if not geojson_path.exists():
        return 0
        
    gdf = gpd.read_file(geojson_path)
    if gdf.empty:
        return 0
        
    if gdf.crs and str(gdf.crs) != str(profile_crs):
        gdf = gdf.to_crs(profile_crs)

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        minx, miny, maxx, maxy = geom.bounds
        px_x0 = (minx - bounds.left) / px_w
        px_y0 = (bounds.top - maxy)   / px_h
        px_w_  = (maxx - minx) / px_w
        px_h_  = (maxy - miny) / px_h

        rect = mpatches.Rectangle(
            (px_x0, px_y0), px_w_, px_h_,
            linewidth=edge_width,
            edgecolor=edge_c,
            facecolor=fill_c,
            alpha=fill_alpha,
        )
        ax.add_patch(rect)
        
        # Label
        cx = px_x0 + px_w_ / 2
        cy = px_y0 + px_h_ / 2
        ax.text(
            cx, cy, f"{label_prefix}-{row.get('plot_id', '')}",
            ha="center", va="center",
            fontsize=5, color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.1", fc="black", alpha=0.4, ec="none"),
        )
    return len(gdf)


# --- 1. OVERLAY BOTH (Plots and Irrigation) ---

def overlay_all_bboxes(
    orthophoto_path: Path,
    plot_bbox_geojson: Path,
    irrigation_bbox_geojson: Path,
    output_png: Path,
    plot_color: str = "lime",
    irrigation_color: str = "cyan",
    fill_alpha: float = 0.15,
    edge_width: float = 1.2,
    figsize: tuple = (18, 18),
    dpi: int = 150,
) -> None:
    """Overlay both farm plots and irrigation bounding boxes on the orthophoto."""
    output_png.parent.mkdir(parents=True, exist_ok=True)
    rgb, profile, bounds = load_rgb_uint8(orthophoto_path)
    
    H, W = rgb.shape[:2]
    px_w = (bounds.right - bounds.left) / W
    px_h = (bounds.top   - bounds.bottom) / H

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi)
    ax.imshow(rgb)

    n_plots = _add_bboxes_to_ax(ax, plot_bbox_geojson, bounds, px_w, px_h, profile["crs"], plot_color, plot_color, fill_alpha, edge_width, "P")
    n_irrig = _add_bboxes_to_ax(ax, irrigation_bbox_geojson, bounds, px_w, px_h, profile["crs"], irrigation_color, irrigation_color, fill_alpha, edge_width, "I")

    legend_elements = [
        mpatches.Patch(facecolor=plot_color, edgecolor=plot_color, alpha=0.5, label=f'Farm Plots ({n_plots})'),
        mpatches.Patch(facecolor=irrigation_color, edgecolor=irrigation_color, alpha=0.5, label=f'Irrigation ({n_irrig})')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=12)

    ax.set_title(f"Classified Farm Plots & Irrigation\n{orthophoto_path.name}", fontsize=14)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_png, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Combined overlay saved → {output_png}")


# --- 2. OVERLAY FARM PLOTS ONLY ---

def overlay_plot_bboxes(
    orthophoto_path: Path,
    plot_bbox_geojson: Path,
    output_png: Path,
    color: str = "lime",
    fill_alpha: float = 0.15,
    edge_width: float = 1.2,
    figsize: tuple = (18, 18),
    dpi: int = 150,
) -> None:
    """Overlay ONLY farm plot bounding boxes on the orthophoto."""
    output_png.parent.mkdir(parents=True, exist_ok=True)
    rgb, profile, bounds = load_rgb_uint8(orthophoto_path)
    
    H, W = rgb.shape[:2]
    px_w = (bounds.right - bounds.left) / W
    px_h = (bounds.top   - bounds.bottom) / H

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi)
    ax.imshow(rgb)

    n_plots = _add_bboxes_to_ax(ax, plot_bbox_geojson, bounds, px_w, px_h, profile["crs"], color, color, fill_alpha, edge_width, "P")

    legend_elements = [mpatches.Patch(facecolor=color, edgecolor=color, alpha=0.5, label=f'Farm Plots ({n_plots})')]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=12)

    ax.set_title(f"Farm Plots Only\n{orthophoto_path.name}", fontsize=14)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_png, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Plot overlay saved → {output_png}")


# --- 3. OVERLAY IRRIGATION ONLY ---

def overlay_irrigation_bboxes(
    orthophoto_path: Path,
    irrigation_bbox_geojson: Path,
    output_png: Path,
    color: str = "cyan",
    fill_alpha: float = 0.15,
    edge_width: float = 1.2,
    figsize: tuple = (18, 18),
    dpi: int = 150,
) -> None:
    """Overlay ONLY irrigation bounding boxes on the orthophoto."""
    output_png.parent.mkdir(parents=True, exist_ok=True)
    rgb, profile, bounds = load_rgb_uint8(orthophoto_path)
    
    H, W = rgb.shape[:2]
    px_w = (bounds.right - bounds.left) / W
    px_h = (bounds.top   - bounds.bottom) / H

    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=dpi)
    ax.imshow(rgb)

    n_irrig = _add_bboxes_to_ax(ax, irrigation_bbox_geojson, bounds, px_w, px_h, profile["crs"], color, color, fill_alpha, edge_width, "I")

    legend_elements = [mpatches.Patch(facecolor=color, edgecolor=color, alpha=0.5, label=f'Irrigation ({n_irrig})')]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=12)

    ax.set_title(f"Irrigation Canals Only\n{orthophoto_path.name}", fontsize=14)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_png, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"Irrigation overlay saved → {output_png}")