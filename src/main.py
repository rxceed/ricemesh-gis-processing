import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from utils import dms_to_decimal, create_bounding_box
from modules import plot_segmentation
from modules import visualize

def main():
    RAW_TIF_PATH = Path.joinpath(Path.cwd(), "dataset/proc/proc_rgb.tif")
    EVI_TIF_PATH = Path.joinpath(Path.cwd(), "dataset/proc/proc_evi.tif")
    NDWI_TIF_PATH = Path.joinpath(Path.cwd(), "dataset/proc/proc_ndwi.tif")
    SRC_PATH = {"raw": RAW_TIF_PATH, "evi": EVI_TIF_PATH, "ndwi": NDWI_TIF_PATH}
    DST_DIR_PATH = Path.joinpath(Path.cwd(), "output")
    #masks, bbox, raw_segment = plot_segmentation.segment_plot(SRC_PATH, DST_DIR_PATH, tile_size=1024, min_area_m2=200, overlap=0)
    masks, bbox, raw_segment = plot_segmentation.segment_plot_samtext(SRC_PATH, DST_DIR_PATH, tile_size=2048, min_area_m2=100, overlap=256)
    visualize.overlay_segments_on_orthophoto(SRC_PATH['raw'], raw_segment, Path.joinpath(DST_DIR_PATH, "overlay_segments.png"))
    visualize.overlay_bboxes_on_orthophoto(SRC_PATH['raw'], bbox['raw'], Path.joinpath(DST_DIR_PATH, "overlay_bboxes.png"))
    visualize.overlay_comparison(SRC_PATH['raw'], raw_segment, bbox['raw'], Path.joinpath(DST_DIR_PATH, "overlay_comparison.png"))
    visualize.overlay_all_bboxes(SRC_PATH['raw'], bbox['plot'], bbox['irrig'], Path.joinpath(DST_DIR_PATH, "overlay_labeled_all.png"))
    visualize.overlay_plot_bboxes(SRC_PATH['raw'], bbox['plot'], Path.joinpath(DST_DIR_PATH, "overlay_labeled_plots.png"))
    visualize.overlay_irrigation_bboxes(SRC_PATH['raw'], bbox['irrig'], Path.joinpath(DST_DIR_PATH, "overlay_labeled_irrigation.png"))
if __name__ == "__main__":
    main()