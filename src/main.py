import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from modules.plot_segmentation import segment_plot_fastsam
from components.segmentation.overlay import overlay_plot_bboxes, overlay_comparison, overlay_bboxes_on_orthophoto, overlay_segments_on_orthophoto
def main():
    # RAW_TIF_PATH = Path.joinpath(Path.cwd(), "dataset/proc/proc_raw.tif")
    # DST_DIR_PATH = Path.joinpath(Path.cwd(), "output")
    # masks, bboxes, raw_vector = segment_plot_fastsam(RAW_TIF_PATH, DST_DIR_PATH, use_vari=False, 
    #                                                  overlap=0, tile_size=4096, iou=0.9, conf=0.3,
    #                                                  model_type=Path.joinpath(Path.cwd(), "best.pt"))
    # overlay_segments_on_orthophoto(RAW_TIF_PATH, raw_vector, Path.joinpath(DST_DIR_PATH, "overlay_segments.png"))
    # overlay_bboxes_on_orthophoto(RAW_TIF_PATH, bboxes['raw'], Path.joinpath(DST_DIR_PATH, "overlay_bbox_raw.png"), edge_color="blue")
    # overlay_plot_bboxes(RAW_TIF_PATH, bboxes['plot'], Path.joinpath(DST_DIR_PATH, "overlay_plot_bbox.png"))
    print("Y")
if __name__ == "__main__":
    main()