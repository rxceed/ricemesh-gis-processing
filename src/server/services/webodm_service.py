import requests
import json
from dotenv import load_dotenv
import os
import tempfile as _tempfile
import math as _math
import rasterio as _rasterio
from rasterio.warp import transform as _transform
from bson import ObjectId

from db.models import WebODMAsset
from db.gridfs_ops import gridfs_delete_file

load_dotenv()

WEBODM_ROOT = os.getenv("WEBODM_ROOT")
WEBODM_USER = os.getenv("WEBODM_USER")
WEBODM_PASS = os.getenv("WEBODM_PASS")

# Default WebODM task options
WEBODM_DEFAULT_OPTIONS = [
    {"name": "auto-boundary", "value": True},
    {"name": "use-hybrid-bundle-adjustment", "value": True},
    {"name": "dsm", "value": True},
    {"name": "dtm", "value": True},
    {"name": "dem-euclidean-map", "value": True},
    {"name": "dem-resolution", "value": 0.5},
    {"name": "orthophoto-resolution", "value": 0.5},
    {"name": "orthophoto-cutline", "value": True},
    {"name": "tiles", "value": True},
]

async def webodm_auth_service():
    """
    Returns:
        token: str
    """
    auth_api_path = f"{WEBODM_ROOT}/api/token-auth/"
    data = {"username": WEBODM_USER, "password": WEBODM_PASS}
    res = requests.post(auth_api_path, data=data)
    res.raise_for_status()
    return res.json()["token"]

async def webodm_project_get_service(token: str, project_id: int = None, name: str = None):
    project_api_path = f"{WEBODM_ROOT}/api/projects/"
    if project_id:
        project_api_path += f"{project_id}/"
    params = {}
    if name:
        params["name"] = name
    res = requests.get(project_api_path, params=params, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return res.json()

async def webodm_project_create_service(data: dict, token: str):
    project_api_path = f"{WEBODM_ROOT}/api/projects/"
    res = requests.post(project_api_path, json=data, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return res.json()

async def webodm_project_update_service(project_id: int, data: dict, token: str):
    project_api_path = f"{WEBODM_ROOT}/api/projects/{project_id}/"
    res = requests.patch(project_api_path, json=data, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return res.json()

async def webodm_project_delete_service(project_id: int, token: str):
    project_api_path = f"{WEBODM_ROOT}/api/projects/{project_id}/"
    res = requests.delete(project_api_path, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return {"status": "deleted"}

async def webodm_task_create_service(project_id: int, file_tuples: list, data: dict, token: str):
    task_api_path = f"{WEBODM_ROOT}/api/projects/{project_id}/tasks/"
    
    payload = {}
    if data.get("name"):
        payload["name"] = data["name"]
    
    # Merge user options with defaults
    user_options = data.get("options", [])
    if user_options is None:
        user_options = []
        
    # Build merged options dictionary
    merged_options = {opt["name"]: opt["value"] for opt in WEBODM_DEFAULT_OPTIONS}
    for opt in user_options:
        # Support both 'name'/'value' and 'k'/'v' keys to prevent KeyError
        name = opt.get("name") if "name" in opt else opt.get("k")
        val = opt.get("value") if "value" in opt else opt.get("v")
        if name:
            merged_options[name] = val
    
    # Construct final options list, filtering out any invalid entries
    final_options = []
    for k, v in merged_options.items():
        if k is not None:
            final_options.append({"name": str(k), "value": v})
            
    payload["options"] = json.dumps(final_options)
    
    # Prepare files for multipart/form-data
    # WebODM accepts multiple images using the 'images' key
    file_payload = [('images', (ft[0], ft[1], ft[2])) for ft in file_tuples]
    
    res = requests.post(task_api_path, data=payload, files=file_payload, headers={"Authorization": f"JWT {token}"})
    
    if res.status_code == 400:
        print(f"WebODM Task Creation 400 Error: {res.text}")
        # Try to parse and print more specific field errors if they exist
        try:
            err_data = res.json()
            print(f"Structured Error Detail: {json.dumps(err_data, indent=2)}")
        except:
            pass
        
    res.raise_for_status()
    return res.json()

async def webodm_task_get_service(project_id: int, token: str, task_id: str = None, name: str = None):
    task_api_path = f"{WEBODM_ROOT}/api/projects/{project_id}/tasks/"
    if task_id:
        task_api_path += f"{task_id}/"
    params = {}
    if name:
        params["name"] = name
    res = requests.get(task_api_path, params=params, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return res.json()

async def webodm_task_delete_service(project_id: int, task_id: str, token: str):
    task_api_path = f"{WEBODM_ROOT}/api/projects/{project_id}/tasks/{task_id}/"
    res = requests.delete(task_api_path, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return {"status": "deleted"}

async def webodm_task_cancel_service(project_id: int, task_id: str, token: str):
    task_api_path = f"{WEBODM_ROOT}/api/projects/{project_id}/tasks/{task_id}/cancel/"
    res = requests.post(task_api_path, headers={"Authorization": f"JWT {token}"})
    res.raise_for_status()
    return res.json()

async def webodm_task_download_service(project_name: str, task_name: str, asset_type: str, token: str):
    """
    Downloads an asset from WebODM by project and task name.
    """
    # 1. Find project
    project_list = await webodm_project_get_service(token, name=project_name)
    if isinstance(project_list, dict):
        results = project_list.get("results", [])
    elif isinstance(project_list, list):
        results = project_list
    else:
        results = []
        
    project = next((p for p in results if p.get("name") == project_name), None)
    if not project:
        raise ValueError(f"Project '{project_name}' not found")
    
    project_id = project["id"]
    
    # 2. Find task
    task_list = await webodm_task_get_service(project_id, token, name=task_name)
    # WebODM /api/projects/{id}/tasks/?name=... returns a list directly
    task = next((t for t in task_list if t.get("name") == task_name), None)
    if not task:
        raise ValueError(f"Task '{task_name}' not found in project '{project_name}'")
    
    task_id = task["id"]
    
    # 3. Download asset
    download_url = f"{WEBODM_ROOT}/api/projects/{project_id}/tasks/{task_id}/download/{asset_type}"
    res = requests.get(download_url, headers={"Authorization": f"JWT {token}"}, stream=True)
    res.raise_for_status()
    
    return res

async def webodm_task_progress_service(project_id: int, task_id: str, token: str) -> dict:
    """
    Fetch a single WebODM task and return a normalised progress snapshot.

    Returns dict with keys:
        status_code  – raw WebODM status int (10=Queued, 20=Running, 30=Failed, 40=Completed)
        status       – human-readable label
        percent      – 0–100 float
        processing_time, last_error, available_assets – pass-through from WebODM
    """
    _STATUS_LABELS = {10: "queued", 20: "running", 30: "failed", 40: "completed", 50: "canceled"}

    task_data = await webodm_task_get_service(project_id, token, task_id=str(task_id))
    status_code = task_data.get("status")
    running_progress = task_data.get("running_progress", 0.0) or 0.0

    return {
        "status_code":      status_code,
        "status":           _STATUS_LABELS.get(status_code, "unknown"),
        "percent":          round(running_progress * 100, 1),
        "processing_time":  task_data.get("processing_time"),
        "last_error":       task_data.get("last_error"),
        "available_assets": task_data.get("available_assets", []),
    }


async def webodm_asset_delete_service(asset_id: str, owner_id: str, db) -> dict:
    asset = await WebODMAsset.find_one({"_id": ObjectId(asset_id), "ownerId": owner_id})
    if not asset:
        raise ValueError("WebODM asset not found or unauthorized")
    
    await gridfs_delete_file(db, asset.gridfs_file_id, bucket_name="webodm_assets")
    await asset.delete()
    return {"status": "OK", "message": f"WebODM asset {asset_id} deleted"}


async def webodm_task_get_dtm_service(
    project_name: str,
    task_name: str,
    token: str,
    max_resolution: int = 100,
    x_crs: str = None,
    x_bounds: str = None,
    x_transform: str = None,
) -> list:
    """
    Downloads dtm.tif from WebODM and extracts coordinates and elevation values.
    Adjusts and scales coordinate points using optional display georeferencing metadata.
    """
    if max_resolution <= 0:
        max_resolution = 100

    # Parse bounds if provided
    min_x, max_x = None, None
    min_y, max_y = None, None
    if x_bounds:
        try:
            left, bottom, right, top = map(float, x_bounds.split(","))
            min_x, max_x = min(left, right), max(left, right)
            min_y, max_y = min(bottom, top), max(bottom, top)
        except Exception as bounds_err:
            print(f"Error parsing x_bounds: {bounds_err}")

    # Parse display transform if provided
    display_transform = None
    if x_transform:
        try:
            coeffs = [float(val.strip()) for val in x_transform.split(",")]
            if len(coeffs) == 6:
                display_transform = _rasterio.Affine(*coeffs)
        except Exception as trans_err:
            print(f"Error parsing x_transform: {trans_err}")

    # 1. Download DTM file from WebODM task download service
    res = await webodm_task_download_service(project_name, task_name, "dtm.tif", token)

    # 2. Save it to a temporary file inside the workspace 'tmp' directory
    os.makedirs("tmp", exist_ok=True)
    fd, tmp_path = _tempfile.mkstemp(dir="tmp", suffix=".tif")
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        # 3. Read and extract coordinate/elevation data
        points = []
        with _rasterio.open(tmp_path) as src:
            # Band 1 usually contains the elevation data
            data = src.read(1)
            h, w = src.height, src.width

            # Determine step size based on max_resolution
            step_y = max(1, h // max_resolution)
            step_x = max(1, w // max_resolution)

            nodata_val = src.nodata

            xs = []
            ys = []
            elevations = []

            for r in range(0, h, step_y):
                for c in range(0, w, step_x):
                    val = data[r, c]
                    # Skip nodata, NaN, and Inf values
                    if nodata_val is not None and val == nodata_val:
                        continue
                    if _math.isnan(val) or _math.isinf(val):
                        continue

                    x, y = src.xy(r, c)
                    xs.append(x)
                    ys.append(y)
                    elevations.append(float(val))

            if xs:
                # Reproject to display CRS if provided and different
                xs_display = xs
                ys_display = ys
                if x_crs and src.crs and x_crs != src.crs.to_string():
                    try:
                        xs_display, ys_display = _transform(src.crs, x_crs, xs, ys)
                    except Exception as proj_err:
                        print(f"Error reprojecting to display CRS: {proj_err}")

                # Transform coordinates from the source CRS to EPSG:4326 (WGS84 lon, lat)
                lons, lats = _transform(src.crs, "EPSG:4326", xs, ys)
                inv_transform = ~display_transform if display_transform else None

                for i in range(len(xs)):
                    x_disp = xs_display[i]
                    y_disp = ys_display[i]

                    # Filter by bounds in the display coordinate space
                    if min_x is not None and not (min_x <= x_disp <= max_x):
                        continue
                    if min_y is not None and not (min_y <= y_disp <= max_y):
                        continue

                    pt = {
                        "lon": lons[i],
                        "lat": lats[i],
                        "elevation": elevations[i]
                    }

                    if inv_transform:
                        pixel_col, pixel_row = inv_transform * (x_disp, y_disp)
                        pt["x"] = round(pixel_col, 2)
                        pt["y"] = round(pixel_row, 2)

                    points.append(pt)
        return points
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
