from server.schemas.webodm_schema import *
from server.services.webodm_service import *
from fastapi import Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from typing import List

async def webodm_project_create(ctx: webodm_project_modelBase):
    try:
        auth_token = await webodm_auth_service()
        data = {"name": ctx.project_name, "description": ctx.project_description}
        res = await webodm_project_create_service(data, auth_token)
        return {"message": "Project created successfully", "project": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_project_get_all(name: str = None):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_project_get_service(auth_token, name=name)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_project_get_one(project_id: int):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_project_get_service(auth_token, project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_project_update(project_id: int, ctx: webodm_project_update_model):
    try:
        auth_token = await webodm_auth_service()
        data = ctx.model_dump(exclude_none=True)
        res = await webodm_project_update_service(project_id, data, auth_token)
        return {"message": "Project updated successfully", "project": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_project_delete(project_id: int):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_project_delete_service(project_id, auth_token)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_task_create(project_id: int, ctx: webodm_task_create_model, files: List[UploadFile] = File(...)):
    try:
        auth_token = await webodm_auth_service()
        
        file_tuples = []
        for file in files:
            content = await file.read()
            file_tuples.append((file.filename, content, file.content_type))
        
        data = ctx.model_dump(exclude_none=True)
        res = await webodm_task_create_service(project_id, file_tuples, data, auth_token)
        return {"message": "Task created successfully", "task": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_task_get_all(project_id: int, name: str = None):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_get_service(project_id, auth_token, name=name)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_task_get_one(project_id: int, task_id: str):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_get_service(project_id, auth_token, task_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_task_delete(project_id: int, task_id: str):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_delete_service(project_id, task_id, auth_token)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_task_download(ctx: webodm_asset_download_model):
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_download_service(ctx.project_name, ctx.task_name, ctx.asset_type, auth_token)
        
        return StreamingResponse(
            res.iter_content(chunk_size=1024*1024),
            media_type=res.headers.get("Content-Type"),
            headers={
                "Content-Disposition": res.headers.get("Content-Disposition", f"attachment; filename={ctx.asset_type}")
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
async def webodm_task_display(ctx: webodm_asset_download_model):
    import io
    from PIL import Image
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_download_service(ctx.project_name, ctx.task_name, ctx.asset_type, auth_token)
        # Load the downloaded binary data into memory
        file_bytes = res.content
        
        # Open the TIFF with Pillow
        image = Image.open(io.BytesIO(file_bytes))
        
        # Convert to RGB (TIFFs might be RGBA or have other bands)
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # Save to a new in-memory buffer as JPEG
        jpeg_buffer = io.BytesIO()
        image.save(jpeg_buffer, format="JPEG", quality=85)
        jpeg_buffer.seek(0)
        
        # Stream the JPEG to the frontend
        return StreamingResponse(
            jpeg_buffer,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"inline; filename={ctx.asset_type.split('.')[0]}.jpg"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def webodm_asset_delete(req: Request, asset_id: str, owner_id: int):
    try:
        return await webodm_asset_delete_service(asset_id, owner_id, db=req.app.state.db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
