import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from components.upscaling import ldsr2
from utils import dms_to_decimal, create_bounding_box
from components.imagery import gee
from modules import plot_segmentation

#IMG Path
#sat_img_path = os.path.abspath(os.path.join(os.getcwd(), "outputs/sat_img_original.png"))
GEE_GEOTIFF_PATH = Path.joinpath(Path.cwd(), "gee_output/tile_0000.tif").resolve()
GEE_OUTPUT_DIR = Path.joinpath(Path.cwd(), "gee_output").resolve()
SEGMENTATION_OUTPUT_DIR = Path.joinpath(Path.cwd(), "segmented_output").resolve()

def main():
    gee.init()

    lat = f"7o26\'38.09\"S" 
    lon = f"112o41\'12.08\"E"
    bbox = create_bounding_box(dms_to_decimal(lat), dms_to_decimal(lon), 10)
    #gee_img = gee.get_sentinel_2_l2a(bbox, 0.3)
    #gee.download_geotiff(gee_img, (gee.GEE_BANDS["sentinel-2-l2a-10m"]+gee.GEE_BANDS["sentinel-2-l2a-20m"]), bbox, GEE_GEOTIFF_PATH)
    #gee.fetch_tiles(bbox, GEE_OUTPUT_DIR, max_cloud_cover=0.3, bands=gee.GEE_BANDS["sentinel-2-l2a-10m"])
    plot_segmentation.segment_plot(GEE_GEOTIFF_PATH, SEGMENTATION_OUTPUT_DIR, 0.45)

    """
    img_path = os.path.abspath(os.path.join(os.getcwd(), "outputs/gee_img_original.png"))
    img = cv2.imread(img_path)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    img = img*1.1
    img = img.clip(0,255).astype(int)
    print(img)
    plt.figure(figsize=(10,10))
    plt.imshow(img)
    plt.axis("off")
    plt.show()
    """

    """
    img = datacube[['red', 'green', 'blue']].isel(time=0)
    img = img.to_array().values.transpose(1,2,0)
    img = (img/3000.0).clip(0,1)
    img_save = cv2.cvtColor(np.uint8((img*255)), cv2.COLOR_RGB2BGR)
    cv2.imwrite(sat_img_path, img_save)
    
    upscaled = cv2.cvtColor(src=cv2.imread(upscaled_img_path), code=cv2.COLOR_BGR2RGB)
    plt.figure("Original image",figsize=(10, 10), )
    plt.imshow(img)
    plt.axis("off")
    plt.figure("Upscaled image",figsize=(10, 10))
    plt.imshow(upscaled)
    plt.axis("off")
    plt.show()
    print("All Done!!!")
    """

if __name__ == "__main__":
    main()