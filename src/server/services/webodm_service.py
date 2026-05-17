import requests
import json
from dotenv import load_dotenv
import os
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
    {"name": "rerun-from", "value": "dataset"}
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

async def webodm_asset_delete_service(asset_id: str, owner_id: int, db) -> dict:
    asset = await WebODMAsset.find_one({"_id": ObjectId(asset_id), "ownerId": owner_id})
    if not asset:
        raise ValueError("WebODM asset not found or unauthorized")
    
    await gridfs_delete_file(db, asset.gridfs_file_id, bucket_name="webodm_assets")
    await asset.delete()
    return {"status": "OK", "message": f"WebODM asset {asset_id} deleted"}
