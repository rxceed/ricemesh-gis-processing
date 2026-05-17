from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from server.controllers.webodm_controller import *
from server.schemas.webodm_schema import *
from typing import List, Optional
import json

webodm_router = APIRouter(prefix="/webodm", tags=["WebODM"])

@webodm_router.post("/projects")
async def create_project(ctx: webodm_project_modelBase):
    return await webodm_project_create(ctx)

@webodm_router.get("/projects")
async def get_projects(name: Optional[str] = None):
    return await webodm_project_get_all(name=name)

@webodm_router.get("/projects/{project_id}")
async def get_project(project_id: int):
    return await webodm_project_get_one(project_id)

@webodm_router.put("/projects/{project_id}")
async def update_project(project_id: int, ctx: webodm_project_update_model):
    return await webodm_project_update(project_id, ctx)

@webodm_router.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    return await webodm_project_delete(project_id)

@webodm_router.post("/projects/{project_id}/tasks")
async def create_task(
    project_id: int,
    name: Optional[str] = Form(None),
    options: Optional[str] = Form(None), # JSON string
    files: List[UploadFile] = File(...)
):
    ctx_data = {}
    if name:
        ctx_data["name"] = name
    if options:
        try:
            ctx_data["options"] = json.loads(options)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format for options")
    
    ctx = webodm_task_create_model(**ctx_data)
    return await webodm_task_create(project_id, ctx, files)

@webodm_router.get("/projects/{project_id}/tasks")
async def get_tasks(project_id: int, name: Optional[str] = None):
    return await webodm_task_get_all(project_id, name=name)

@webodm_router.get("/projects/{project_id}/tasks/{task_id}")
async def get_task(project_id: int, task_id: str):
    return await webodm_task_get_one(project_id, task_id)

@webodm_router.delete("/projects/{project_id}/tasks/{task_id}")
async def delete_task(project_id: int, task_id: str):
    return await webodm_task_delete(project_id, task_id)

@webodm_router.get("/download")
async def download_asset(ctx: webodm_asset_download_model = Depends()):
    return await webodm_task_download(ctx)

@webodm_router.get("/display")
async def download_asset(ctx: webodm_asset_download_model = Depends()):
    return await webodm_task_display(ctx)

@webodm_router.delete("/assets/{asset_id}")
async def delete_asset(req: Request, asset_id: str, owner_id: int):
    return await webodm_asset_delete(req, asset_id, owner_id)
