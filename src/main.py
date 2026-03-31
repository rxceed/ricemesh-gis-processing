from pystac_client import Client
import odc.stac
import dask.distributed
import matplotlib.pyplot as plt
import numpy as np
import dotenv
import os
import subprocess, sys
import cv2

from utils import dms_to_decimal, create_bounding_box

#Env
dotenv.load_dotenv()
STAC_ENDPOINT = os.getenv("STAC_ENDPOINT")

#IMG Path
sat_img_path = os.path.abspath(os.path.join(os.getcwd(), "outputs/sat_img_original.png"))
upscaled_img_path = os.path.abspath(os.path.join(os.getcwd(), "outputs/sat_img_upscale.png"))

#ESRGAN
esrgan_exec = os.path.abspath(os.path.join(os.getcwd(), "realesrgan/realesrgan-ncnn-vulkan"))
esrgan_args = ["-i", sat_img_path, "-o", upscaled_img_path]

def main():
    endpoint = STAC_ENDPOINT
    catalog = Client.open(endpoint)
    dask_client = dask.distributed.Client()
    print(dask_client.dashboard_link)

    lat = f"7o26\'38.09\"S" 
    lon = f"112o41\'12.08\"E"
    bb = create_bounding_box(dms_to_decimal(lat), dms_to_decimal(lon), 9)

    stac_search = catalog.search(
        bbox=bb,
        collections=["sentinel-2-l2a"],
        query={"eo:cloud_cover": {"lt": 15}},
        sortby=[{"field": "properties.datetime", "direction": "desc"}],
        max_items=1
    )
    stac_items = stac_search.item_collection()
    print(f"Found {len(stac_items)} items")

    odc.stac.configure_rio(cloud_defaults=True, verbose=True, aws={"aws_unsigned": True})
    datacube_loaded = odc.stac.load(
        stac_items,
        bands=["red", "green", "blue"],
        resolution=10,
        bbox=bb,
        chunks={"x": 2048, "y": 2048},
    )
    print('Done')
    print(datacube_loaded)
    datacube = datacube_loaded.compute()
    img = datacube[['red', 'green', 'blue']].isel(time=0)
    img = img.to_array().values.transpose(1,2,0)
    img = (img/3000.0).clip(0,1)
    img_save = cv2.cvtColor(np.uint8((img*255)), cv2.COLOR_RGB2BGR)
    cv2.imwrite(sat_img_path, img_save)

    esrgan = subprocess.run([esrgan_exec, esrgan_args[0], esrgan_args[1], esrgan_args[2], esrgan_args[3]], capture_output=True, text=True, check=True)
    print("Output:", esrgan.stdout)
    print("Error:", esrgan.stderr)
    print("Exit code:", esrgan.returncode)
    
    upscaled = cv2.cvtColor(cv2.imread(upscaled_img_path), cv2.COLOR_BGR2RGB)
    plt.figure("Original image",figsize=(10, 10), )
    plt.imshow(img)
    plt.axis("off")
    plt.figure("Upscaled image",figsize=(10, 10))
    plt.imshow(upscaled)
    plt.axis("off")
    plt.show()
    print("All Done!!!")

if __name__ == "__main__":
    main()