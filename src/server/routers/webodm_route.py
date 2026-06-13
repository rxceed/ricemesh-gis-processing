from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json

from server.schemas.webodm_schema import (
    webodm_project_modelBase          as _webodm_project_modelBase,
    webodm_project_update_model       as _webodm_project_update_model,
    webodm_task_create_model          as _webodm_task_create_model,
    webodm_asset_download_model       as _webodm_asset_download_model,
    webodm_project_model              as _webodm_project_model,
    webodm_project_list_response      as _webodm_project_list_response,
    webodm_project_create_response    as _webodm_project_create_response,
    webodm_project_update_response    as _webodm_project_update_response,
    webodm_delete_response            as _webodm_delete_response,
    webodm_task_model                 as _webodm_task_model,
    webodm_task_create_response       as _webodm_task_create_response,
    webodm_task_list_response         as _webodm_task_list_response,
    webodm_asset_delete_response      as _webodm_asset_delete_response,
    webodm_dtm_response               as _webodm_dtm_response,
)
from server.controllers.webodm_controller import (
    webodm_project_create  as _webodm_project_create,
    webodm_project_get_all as _webodm_project_get_all,
    webodm_project_get_one as _webodm_project_get_one,
    webodm_project_update  as _webodm_project_update,
    webodm_project_delete  as _webodm_project_delete,
    webodm_task_create     as _webodm_task_create,
    webodm_task_get_all    as _webodm_task_get_all,
    webodm_task_get_one    as _webodm_task_get_one,
    webodm_task_progress   as _webodm_task_progress,
    webodm_task_delete     as _webodm_task_delete,
    webodm_task_download   as _webodm_task_download,
    webodm_task_display    as _webodm_task_display,
    webodm_task_stream     as _webodm_task_stream,
    webodm_asset_delete    as _webodm_asset_delete,
    webodm_task_get_dtm    as _webodm_task_get_dtm,
)

webodm_router = APIRouter(prefix="/webodm", tags=["WebODM"])


@webodm_router.post("/projects", response_model=_webodm_project_create_response)
async def create_project(ctx: _webodm_project_modelBase):
    return await _webodm_project_create(ctx)


@webodm_router.get("/projects", response_model=_webodm_project_list_response)
async def get_projects(name: Optional[str] = None):
    return await _webodm_project_get_all(name=name)


@webodm_router.get("/projects/{project_id}", response_model=_webodm_project_model)
async def get_project(project_id: int):
    return await _webodm_project_get_one(project_id)


@webodm_router.put("/projects/{project_id}", response_model=_webodm_project_update_response)
async def update_project(project_id: int, ctx: _webodm_project_update_model):
    return await _webodm_project_update(project_id, ctx)


@webodm_router.delete("/projects/{project_id}", response_model=_webodm_delete_response)
async def delete_project(project_id: int):
    return await _webodm_project_delete(project_id)


@webodm_router.post("/projects/{project_id}/tasks", response_model=_webodm_task_create_response)
async def create_task(
    project_id: int,
    name: Optional[str] = Form(None),
    options: Optional[str] = Form(None),  # JSON string
    files: List[UploadFile] = File(...),
):
    ctx_data = {}
    if name:
        ctx_data["name"] = name
    if options:
        try:
            ctx_data["options"] = json.loads(options)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format for options")

    ctx = _webodm_task_create_model(**ctx_data)
    return await _webodm_task_create(project_id, ctx, files)


@webodm_router.get("/projects/{project_id}/tasks", response_model=_webodm_task_list_response)
async def get_tasks(project_id: int, name: Optional[str] = None):
    return await _webodm_task_get_all(project_id, name=name)


@webodm_router.get("/projects/{project_id}/tasks/{task_id}", response_model=_webodm_task_model)
async def get_task(project_id: int, task_id: str):
    return await _webodm_task_get_one(project_id, task_id)


@webodm_router.get("/projects/{project_id}/tasks/{task_id}/progress")
async def get_task_progress(project_id: int, task_id: str):
    """Return a normalised progress snapshot for a single WebODM task."""
    return await _webodm_task_progress(project_id, task_id)


@webodm_router.get("/projects/{project_name}/tasks/{task_id}/stream")
async def stream_task_progress(project_name: str, task_id: str):
    """
    Server-Sent Events stream — pushes WebODM task progress every 3 seconds
    until the task completes, fails, or times out.

    Connect with EventSource in JS:
        const es = new EventSource('/webodm/projects/{project_name}/tasks/{task_id}/stream')
        es.onmessage = e => console.log(JSON.parse(e.data))
    """
    return await _webodm_task_stream(project_name, task_id)


@webodm_router.delete("/projects/{project_id}/tasks/{task_id}", response_model=_webodm_delete_response)
async def delete_task(project_id: int, task_id: str):
    return await _webodm_task_delete(project_id, task_id)


@webodm_router.get("/download")
async def download_asset(ctx: _webodm_asset_download_model = Depends()):
    # StreamingResponse cannot be described with response_model
    return await _webodm_task_download(ctx)


@webodm_router.get("/display")
async def display_asset(
    ctx: _webodm_asset_download_model = Depends(),
    max_dim: Optional[int] = 1024,
    quality: Optional[int] = 85
):
    # StreamingResponse cannot be described with response_model
    return await _webodm_task_display(ctx, max_dim=max_dim, quality=quality)


@webodm_router.delete("/assets/{asset_id}", response_model=_webodm_asset_delete_response)
async def delete_asset(req: Request, asset_id: str, owner_id: str):
    return await _webodm_asset_delete(req, asset_id, owner_id)


@webodm_router.get("/projects/{project_name}/tasks/{task_name}/dtm", response_model=_webodm_dtm_response)
async def get_task_dtm(
    project_name: str,
    task_name: str,
    max_resolution: Optional[int] = 100,
    x_crs: Optional[str] = None,
    x_bounds: Optional[str] = None,
    x_transform: Optional[str] = None,
):
    """
    Get digital terrain model (DTM) data from WebODM.
    Extracts coordinate (lon, lat) and elevation values, optionally adjusted and scaled 
    using coordinate system, bounding box bounds, and transform matrix.
    """
    return await _webodm_task_get_dtm(
        project_name, task_name, max_resolution, x_crs, x_bounds, x_transform
    )

