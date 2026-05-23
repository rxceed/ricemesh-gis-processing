from pathlib import Path
from modules.segmentation import fastsam, export_bboxes

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
        raw_mask, raw_vector = fastsam.segment_orthophoto_fastsam_vari(src_tif, dst_dir, 
                                                                        tile_size=tile_size, min_area_m2=min_area_m2, overlap=overlap,
                                                                        iou=iou, conf=conf,
                                                                        model_variant=model_type)
    else:
        raw_mask, raw_vector = fastsam.segment_orthophoto_fastsam_rgb(src_tif, dst_dir, 
                                                                tile_size=tile_size, min_area_m2=min_area_m2, overlap=overlap, 
                                                                iou=iou, conf=conf,
                                                                model_variant=model_type)
    export_bboxes(raw_vector, src_tif, raw_bbox)
    mask_path = {'raw': raw_mask}
    bbox_path = {'raw': raw_bbox}
    return mask_path, bbox_path, raw_vector
