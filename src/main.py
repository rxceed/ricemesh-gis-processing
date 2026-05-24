import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

#from modules.plot_segmentation import segment_plot_fastsam
#from modules.segmentation.overlay import overlay_plot_bboxes, overlay_comparison, overlay_bboxes_on_orthophoto, overlay_segments_on_orthophoto
def main():
    # RAW_TIF_PATH = Path.joinpath(Path.cwd(), "dataset/proc/proc_raw.tif")
    # DST_DIR_PATH = Path.joinpath(Path.cwd(), "output")
    # masks, bboxes, raw_vector = segment_plot_fastsam(RAW_TIF_PATH, DST_DIR_PATH, use_vari=False, 
    #                                                  overlap=0, tile_size=4096, iou=0.9, conf=0.3,
    #                                                  model_type=Path.joinpath(Path.cwd(), "src/modules/segmentation/weight.pt"))
    # overlay_segments_on_orthophoto(RAW_TIF_PATH, raw_vector, Path.joinpath(DST_DIR_PATH, "overlay_segments.png"))
    # overlay_bboxes_on_orthophoto(RAW_TIF_PATH, bboxes['raw'], Path.joinpath(DST_DIR_PATH, "overlay_bbox_raw.png"), edge_color="blue")
    # #overlay_plot_bboxes(RAW_TIF_PATH, bboxes['plot'], Path.joinpath(DST_DIR_PATH, "overlay_plot_bbox.png"))
    from utils.geometry import decode_geometry_4326, decode_point_4326, geodesic_distance_m, component_distance_m
    data = "0103000020E610000001000000050000003333333333B35A40CDCCCCCCCCCC18C0A4703D0AD7B35A40CDCCCCCCCCCC18C0A4703D0AD7B35A40D7A3703D0AD718C03333333333B35A40D7A3703D0AD718C03333333333B35A40CDCCCCCCCCCC18C0"
    decode = decode_geometry_4326(data)
    point1 = decode["coordinates"][0][0]
    point2 = decode["coordinates"][0][2]
    print(point1)
    print(point2)
    print(geodesic_distance_m(point1, point2))
    lon, lat = component_distance_m(point1, point2)
    print(lon, lat)
    print("Y")
if __name__ == "__main__":
    main()