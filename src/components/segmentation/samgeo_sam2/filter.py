# module_filter_classify.py

from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape

# Import your existing bounding box function
# Assuming you saved your bbox code in a file named `module_bbox.py`
from .bbox import export_bboxes

def filter_and_classify_segments(
    sam_mask_tif: Path,
    evi_tif: Path,
    ndwi_tif: Path,
    output_dir: Path,
    evi_threshold: float = 0.2,   # Adjust based on your EVI distribution for crops
    ndwi_threshold: float = 0.1,  # Adjust based on your NDWI distribution for water
):
    """
    Classifies general SAM2 segments into Farm Plots and Irrigation Canals
    using zonal statistics (mean EVI/NDWI per segment).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = sam_mask_tif.stem.replace("_mask", "")
    
    print("Loading rasters for classification...")
    with rasterio.open(sam_mask_tif) as src_mask:
        mask = src_mask.read(1)
        profile = src_mask.profile
        transform = src_mask.transform
        crs = src_mask.crs

    with rasterio.open(evi_tif) as src_evi:
        evi = src_evi.read(1)*-1.0
        
    with rasterio.open(ndwi_tif) as src_ndwi:
        ndwi = src_ndwi.read(1)

    print("Calculating mean EVI and NDWI per segment...")
    # Fast Zonal Statistics using bincount (avoids slow loops over unique IDs)
    valid_pixels = mask > 0
    flat_mask = mask[valid_pixels]
    
    # Calculate counts and sums
    counts = np.bincount(flat_mask)
    sum_evi = np.bincount(flat_mask, weights=evi[valid_pixels])
    sum_ndwi = np.bincount(flat_mask, weights=ndwi[valid_pixels])
    
    # Calculate means safely (avoid division by zero)
    valid_counts = counts > 0
    mean_evi = np.zeros_like(sum_evi)
    mean_ndwi = np.zeros_like(sum_ndwi)
    
    mean_evi[valid_counts] = sum_evi[valid_counts] / counts[valid_counts]
    mean_ndwi[valid_counts] = sum_ndwi[valid_counts] / counts[valid_counts]
    
    print("Applying thresholds...")
    # Logic: High NDWI is irrigation. High EVI (but not high NDWI) is farm plot.
    # Everything else (roads, buildings, low vegetation) is ignored.
    is_irrigation = (mean_ndwi > ndwi_threshold) & valid_counts
    is_plot = ~(((mean_evi > evi_threshold) & (mean_ndwi <= ndwi_threshold)) & valid_counts)
    
    # Create lookup arrays and apply to original mask
    irrigation_lookup = np.zeros(len(counts), dtype=mask.dtype)
    irrigation_lookup[is_irrigation] = np.arange(len(counts))[is_irrigation]
    
    plot_lookup = np.zeros(len(counts), dtype=mask.dtype)
    plot_lookup[is_plot] = np.arange(len(counts))[is_plot]
    
    irrigation_mask = irrigation_lookup[mask]
    plot_mask = plot_lookup[mask]

    print(f"Found {np.sum(is_plot)} farm plots and {np.sum(is_irrigation)} irrigation segments.")

    # --- SAVE OUTPUTS ---
    plot_tif = output_dir / f"{stem}_plot_mask.tif"
    irrigation_tif = output_dir / f"{stem}_irrigation_mask.tif"
    
    # Write Farm Plot TIF
    with rasterio.open(plot_tif, "w", **profile) as dst:
        dst.write(plot_mask, 1)
        
    # Write Irrigation TIF
    with rasterio.open(irrigation_tif, "w", **profile) as dst:
        dst.write(irrigation_mask, 1)

    print("Generating vector polygons and bounding boxes...")
    # Helper to generate base geojson before feeding to your bbox code
    def mask_to_base_geojson(mask_array, out_path):
        results = (
            {'properties': {'value': v}, 'geometry': s}
            for i, (s, v) in enumerate(shapes(mask_array, mask=mask_array>0, transform=transform))
        )
        gdf = gpd.GeoDataFrame.from_features(list(results), crs=crs)
        if not gdf.empty:
            gdf.to_file(out_path, driver="GeoJSON")
        return out_path

    # Process Farm Plots
    plot_base_geo = output_dir / f"{stem}_plot_base.geojson"
    plot_bbox_geo = output_dir / f"{stem}_plot_bbox.geojson"
    if np.sum(is_plot) > 0:
        mask_to_base_geojson(plot_mask, plot_base_geo)
        export_bboxes(plot_base_geo, plot_tif, plot_bbox_geo)
    
    # Process Irrigation
    irrig_base_geo = output_dir / f"{stem}_irrigation_base.geojson"
    irrig_bbox_geo = output_dir / f"{stem}_irrigation_bbox.geojson"
    if np.sum(is_irrigation) > 0:
        mask_to_base_geojson(irrigation_mask, irrig_base_geo)
        # We can pass permissive thresholds to irrigation since canals are thin and long
        export_bboxes(irrig_base_geo, irrigation_tif, irrig_bbox_geo, min_area_ha=0.001, min_compactness=0.01)

    # Clean up base geojsons to leave only the bboxes and tifs
    if plot_base_geo.exists(): plot_base_geo.unlink()
    if irrig_base_geo.exists(): irrig_base_geo.unlink()

    print("Filtering and classification complete!")
    return plot_tif, plot_bbox_geo, irrigation_tif, irrig_bbox_geo