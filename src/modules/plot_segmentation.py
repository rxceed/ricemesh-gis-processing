from pathlib import Path
from components.segmentation import samgeo_sam2, fastsam_yolo, export_bboxes, filter_and_classify_segments_vari

def segment_plot(src_tif: dict[Path], dst_dir: Path, tile_size:int=1024, min_area_m2:int=100, overlap:int=128):
    dst_dir.mkdir(parents=True, exist_ok=True)
    src_tif_raw = src_tif["raw"]
    src_tif_ndvi = src_tif["ndvi"]
    src_tif_evi = src_tif["evi"]
    src_tif_ndwi = src_tif["ndwi"]
    raw_mask, raw_vector = samgeo_sam2.segment_orthophoto_sam2(src_tif_ndvi, dst_dir, tile_size, min_area_m2=min_area_m2, overlap=overlap)
    raw_bbox = Path.joinpath(dst_dir, "raw_bbox.geojson")
    samgeo_sam2.export_bboxes(raw_vector, raw_mask, raw_bbox)
    plot_mask, plot_bbox, irrig_mask, irrig_bbox = samgeo_sam2.filter_and_classify_segments(raw_mask, src_tif_evi, src_tif_ndwi, dst_dir, 
                                                                                            evi_threshold=0.2, ndwi_threshold=0.1)
    mask_path = {'raw': raw_mask, 'plot': plot_mask, 'irrig': irrig_mask}
    bbox_path = {'raw': raw_bbox, 'plot': plot_bbox, 'irrig': irrig_bbox}
    return mask_path, bbox_path, raw_vector

def segment_plot_fastsam(src_tif: dict, dst_dir: Path, use_vari:bool=True, model_type:str="FastSAM-x.pt",
                        tile_size:int=2048, min_area_m2:int=100, overlap:int=0, iou:float=0.9, conf:float=0.4
                        ):
    """
    Parameters
    ----------
    src_tif         : path to input RGB orthophoto as GeoTIFF. Must be georeferenced (carry CRS and affine transform) for valid downstream outputs.
    dst_dir         : Path to directory where outputs will be saved. Created if it doesn't exist.
    use_vari        : Whether to compute VARI and use it as an additional input channel for FastSAM. Improves plot/water separation but adds overhead.
    model_type      : Which FastSAM model variant to use. Options:
                        "FastSAM-s.pt"  (~27 MB)   Fastest, good for large homogeneous objects like whole plots.
                        "FastSAM-m.pt"  (~70 MB)   Balanced   option for general use
    options         : {
                        tile_size, min_area_m2, max_area_m2, overlap, iou, conf, vari_threshold
                        }
    
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    raw_bbox = Path.joinpath(dst_dir, "raw_bbox.geojson")
    if use_vari:
        raw_mask, raw_vector = fastsam_yolo.segment_orthophoto_fastsam_vari(src_tif, dst_dir, 
                                                                        tile_size=tile_size, min_area_m2=min_area_m2, overlap=overlap,
                                                                        iou=iou, conf=conf,
                                                                        model_variant=model_type)
    else:
        raw_mask, raw_vector = fastsam_yolo.segment_orthophoto_fastsam_rgb(src_tif, dst_dir, 
                                                                tile_size=tile_size, min_area_m2=min_area_m2, overlap=overlap, 
                                                                iou=iou, conf=conf,
                                                                model_variant=model_type)
    export_bboxes(raw_vector, src_tif, raw_bbox)
    plot_mask, plot_bbox, irrig_mask, irrig_bbox = filter_and_classify_segments_vari(raw_mask, src_tif, dst_dir, vari_threshold=0.05)
    mask_path = {'raw': raw_mask, 'plot': plot_mask, 'irrig': irrig_mask}
    bbox_path = {'raw': raw_bbox, 'plot': plot_bbox, 'irrig': irrig_bbox}
    return mask_path, bbox_path, raw_vector
