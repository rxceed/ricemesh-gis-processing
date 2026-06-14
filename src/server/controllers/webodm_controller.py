import asyncio
import requests

from server.schemas.webodm_schema import *
from server.services.webodm_service import *
from arq_worker.tasks.videoOps_task import stream_webodm_task_progress as _stream_webodm_task_progress
from fastapi import Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from typing import List


async def webodm_project_create(ctx: webodm_project_modelBase) -> webodm_project_create_response:
    try:
        auth_token = await webodm_auth_service()
        data = {"name": ctx.project_name, "description": ctx.project_description}
        res = await webodm_project_create_service(data, auth_token)
        return webodm_project_create_response(message="Project created successfully", project=res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_project_get_all(name: str = None) -> webodm_project_list_response:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_project_get_service(auth_token, name=name)
        # WebODM /api/projects/ returns a paginated object: {count, next, previous, results}
        if isinstance(res, dict) and "results" in res:
            return webodm_project_list_response(**res)
        # Fallback: raw list (older WebODM versions)
        return webodm_project_list_response(count=len(res), results=res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_project_get_one(project_id: int) -> webodm_project_model:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_project_get_service(auth_token, project_id)
        return webodm_project_model(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_project_update(project_id: int, ctx: webodm_project_update_model) -> webodm_project_update_response:
    try:
        auth_token = await webodm_auth_service()
        data = ctx.model_dump(exclude_none=True)
        res = await webodm_project_update_service(project_id, data, auth_token)
        return webodm_project_update_response(message="Project updated successfully", project=res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_project_delete(project_id: int) -> webodm_delete_response:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_project_delete_service(project_id, auth_token)
        return webodm_delete_response(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_create(
    project_id: int,
    ctx: webodm_task_create_model,
    files: List[UploadFile] = File(...),
) -> webodm_task_create_response:
    try:
        auth_token = await webodm_auth_service()

        file_tuples = []
        for file in files:
            content = await file.read()
            file_tuples.append((file.filename, content, file.content_type))

        data = ctx.model_dump(exclude_none=True)
        res = await webodm_task_create_service(project_id, file_tuples, data, auth_token)
        return webodm_task_create_response(message="Task created successfully", task=res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_get_all(project_id: int, name: str = None) -> webodm_task_list_response:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_get_service(project_id, auth_token, name=name)
        # WebODM task list returns a plain list
        results = res if isinstance(res, list) else res.get("results", [])
        return webodm_task_list_response(results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_get_one(project_id: int, task_id: str) -> webodm_task_model:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_get_service(project_id, auth_token, task_id)
        return webodm_task_model(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_delete(project_id: int, task_id: str) -> webodm_delete_response:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_delete_service(project_id, task_id, auth_token)
        return webodm_delete_response(**res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_download(ctx: webodm_asset_download_model) -> StreamingResponse:
    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_download_service(ctx.project_name, ctx.task_name, ctx.asset_type, auth_token)

        return StreamingResponse(
            res.iter_content(chunk_size=1024 * 1024),
            media_type=res.headers.get("Content-Type"),
            headers={
                "Content-Disposition": res.headers.get(
                    "Content-Disposition",
                    f"attachment; filename={ctx.asset_type}",
                )
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_display(ctx: webodm_asset_download_model) -> StreamingResponse:
    import io
    from PIL import Image

    try:
        auth_token = await webodm_auth_service()
        res = await webodm_task_download_service(ctx.project_name, ctx.task_name, ctx.asset_type, auth_token)

        file_bytes = res.content

        image = Image.open(io.BytesIO(file_bytes))

        if image.mode != "RGB":
            image = image.convert("RGB")

        jpeg_buffer = io.BytesIO()
        image.save(jpeg_buffer, format="JPEG", quality=85)
        jpeg_buffer.seek(0)

        return StreamingResponse(
            jpeg_buffer,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"inline; filename={ctx.asset_type.split('.')[0]}.jpg"
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_asset_delete(req: Request, asset_id: str, owner_id: str) -> webodm_asset_delete_response:
    try:
        res = await webodm_asset_delete_service(asset_id, owner_id, db=req.app.state.db)
        return webodm_asset_delete_response(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_stream(project_id: int, task_id: str) -> StreamingResponse:
    """
    SSE endpoint that polls WebODM for a single task's live progress and
    pushes updates to the client until the task finishes or times out.

    Connect with EventSource in JS:
        const es = new EventSource('/webodm/projects/{project_id}/tasks/{task_id}/stream')
        es.onmessage = e => console.log(JSON.parse(e.data))
    """
    return StreamingResponse(
        _stream_webodm_task_progress(project_id, task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
