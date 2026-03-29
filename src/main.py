from pystac_client import Client
import odc.stac
import dask.distributed
import matplotlib.pyplot as plt
import numpy as np
import dotenv
import os

from utils import dms_to_decimal

#Env
dotenv.load_dotenv()
STAC_ENDPOINT = os.getenv("STAC_ENDPOINT")

def main():
    endpoint = STAC_ENDPOINT
    catalog = Client.open(endpoint)

    dask_client = dask.distributed.Client()
    print(dask_client.dashboard_link)
    
    min_lat_dms = f"7o36\'39.20\"S"
    min_lon_dms = f"112o42\'03.62\"E"
    max_lat_dms = f"7o36\'25.10\"S"
    max_lon_dms = f"112o42\'16.16\"E"
    
    aoi = [dms_to_decimal(min_lon_dms), dms_to_decimal(min_lat_dms), dms_to_decimal(max_lon_dms), dms_to_decimal(max_lat_dms)]

    stac_search = catalog.search(
        bbox=aoi,
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
        bbox=aoi,
        chunks={"x": 2048, "y": 2048},
    )
    print('Done')
    print(datacube_loaded)
    datacube = datacube_loaded.compute()
    img = datacube[['red', 'green', 'blue']].isel(time=0)
    img = img.to_array().values.transpose(1,2,0)
    img = (img/3000.0).clip(0,1)
    plt.figure(figsize=(10, 10))
    plt.imshow(img)
    plt.axis("off")
    plt.show()
    print("All Done!!!")

if __name__ == "__main__":
    main()