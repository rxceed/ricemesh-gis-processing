from pathlib import Path
from components.upscaling import ldsr2
from components.segmentation import samgeo_sam2

def segment_plot(src_tif: dict[Path], dst_dir: Path, tile_size:int=1024, min_area_m2:int=100, overlap:int=128):
    dst_dir.mkdir(parents=True, exist_ok=True)
    src_tif_raw = src_tif["raw"]
    src_tif_evi = src_tif["evi"]
    src_tif_ndwi = src_tif["ndwi"]
    raw_mask, raw_vector = samgeo_sam2.segment_orthophoto_sam2(src_tif_raw, dst_dir, tile_size, min_area_m2=min_area_m2, overlap=overlap)
    raw_bbox = Path.joinpath(dst_dir, "raw_bbox.geojson")
    samgeo_sam2.export_bboxes(raw_vector, raw_mask, raw_bbox)
    plot_mask, plot_bbox, irrig_mask, irrig_bbox = samgeo_sam2.filter_and_classify_segments(raw_mask, src_tif_evi, src_tif_ndwi, dst_dir, 
                                                                                            evi_threshold=0.2, ndwi_threshold=0.1)
    mask_path = {'raw': raw_mask, 'plot': plot_mask, 'irrig': irrig_mask}
    bbox_path = {'raw': raw_bbox, 'plot': plot_bbox, 'irrig': irrig_bbox}
    return mask_path, bbox_path, raw_vector

def segment_plot_samtext(src_tif: dict[Path], dst_dir: Path, tile_size:int=1024, min_area_m2:int=100, overlap:int=128):
    dst_dir.mkdir(parents=True, exist_ok=True)
    src_tif_raw = src_tif["raw"]
    src_tif_evi = src_tif["evi"]
    src_tif_ndwi = src_tif["ndwi"]
    raw_mask, raw_vector = samgeo_sam2.segment_orthophoto_samtext(src_tif_raw, dst_dir, 
                                                                text_prompt="green rectangular paddy field", 
                                                                tile_size=tile_size, min_area_m2=min_area_m2, overlap=overlap,
                                                                box_threshold=0.15, text_threshold=0.15)
    raw_bbox = Path.joinpath(dst_dir, "raw_bbox.geojson")
    samgeo_sam2.export_bboxes(raw_vector, raw_mask, raw_bbox)
    plot_mask, plot_bbox, irrig_mask, irrig_bbox = samgeo_sam2.filter_and_classify_segments(raw_mask, src_tif_evi, src_tif_ndwi, dst_dir, 
                                                                                            evi_threshold=0.2, ndwi_threshold=0.1)
    mask_path = {'raw': raw_mask, 'plot': plot_mask, 'irrig': irrig_mask}
    bbox_path = {'raw': raw_bbox, 'plot': plot_bbox, 'irrig': irrig_bbox}
    return mask_path, bbox_path, raw_vector