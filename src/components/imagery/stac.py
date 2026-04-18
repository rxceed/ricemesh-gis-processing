import pystac_client
import odc.stac
import dask.distributed
import dotenv
import os
import xarray

dotenv.load_dotenv()
STAC_ENDPOINT = os.getenv("STAC_ENDPOINT")

# Initialize PyStac client
def init_client() -> pystac_client.Client:
    endpoint = STAC_ENDPOINT
    stac_client = pystac_client.Client.open(endpoint)
    dask_client = dask.distributed.Client()
    print(dask_client.dashboard_link)
    odc.stac.configure_rio(cloud_defaults=True, verbose=True, aws={"aws_unsigned": True})
    return stac_client

# Search and get Sentinel-2-L2A image
def get_sentinel_2_l2a(stac_client: pystac_client.Client, bbox: list[float], max_cloud_cover:float=15) -> xarray.Dataset:
    stac_search = stac_client.search(
            bbox=bbox,
            collections=["sentinel-2-l2a"],
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
            sortby=[{"field": "properties.datetime", "direction": "desc"}],
            max_items=1
        )
    stac_items = stac_search.item_collection()
    print(f"Found {len(stac_items)} items")
    datacube_loaded = odc.stac.load(
        stac_items,
        bands=["red", "green", "blue"],
        resolution=10,
        bbox=bbox,
        chunks={"x": 2048, "y": 2048},
    )
    print(datacube_loaded)
    datacube = datacube_loaded.compute()
    return datacube