from pathlib import Path
from components.upscaling import ldsr2
from components.segmentation import samgeo_sam2

def segment_plot_(src_tif: Path, dst_dir: Path, ndvi_threshold: float = 0.15):
    dst_dir.mkdir(parents=True, exist_ok=True)
    SAM2_PREP_TIF_NIR_PATH = Path.joinpath(dst_dir, "sam2_prep_nir.tif").resolve()
    SAM2_PREP_TIF_NDVI_PATH = Path.joinpath(dst_dir, "sam2_prep_ndvi.tif").resolve()
    SAM2_MASK_TIF_PATH = Path.joinpath(dst_dir, "sam2_mask.tif").resolve()
    SAM2_VECTOR_GJSON_PATH = Path.joinpath(dst_dir, "sam2_vector.json").resolve()
    FILTERED_GPKG_PATH = Path.joinpath(dst_dir, "filtered_plot.gpkg").resolve()
    NDVI_THRESHOLD = ndvi_threshold
    ldsr_model = ldsr2.load_ldsr_model()
    sr_output = ldsr2.run_ldsr_on_geotiff(ldsr_model, src_tif)
    _, ndvi, profile = samgeo_sam2.sam_prep_ndvi(sr_output, SAM2_PREP_TIF_NDVI_PATH, SAM2_PREP_TIF_NIR_PATH)
    
    import matplotlib.pyplot as plt
    plt.hist(ndvi.flatten(), bins=100, range=(-0.2, 0.8))
    plt.axvline(NDVI_THRESHOLD, color='r', label='current threshold')
    plt.xlabel("NDVI")
    plt.ylabel("Pixel count")
    plt.title("NDVI distribution — pick threshold at the valley between soil and vegetation")
    plt.legend()
    plt.savefig("ndvi_histogram.png")

    samgeo_sam2.run_sam2_automatic(SAM2_PREP_TIF_NDVI_PATH, SAM2_MASK_TIF_PATH, SAM2_VECTOR_GJSON_PATH)
    samgeo_sam2.filter_farm_plots(SAM2_VECTOR_GJSON_PATH, src_tif, ndvi, profile, FILTERED_GPKG_PATH, NDVI_THRESHOLD)

