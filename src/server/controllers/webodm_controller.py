from server.schemas.webodm_schema import *
from server.services.webodm_service import *
from server.controllers.videoOps_controller import stream_webodm_task_progress as _stream_webodm_task_progress
from fastapi import Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from typing import List, Optional


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


async def webodm_task_progress(project_id: int, task_id: str) -> dict:
    """Return a normalised progress snapshot for a single WebODM task."""
    try:
        auth_token = await webodm_auth_service()
        return await webodm_task_progress_service(project_id, task_id, auth_token)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def webodm_task_display(
    ctx: webodm_asset_download_model,
    max_dim: Optional[int] = 1024,
    quality: Optional[int] = 85
) -> StreamingResponse:
    import io
    from PIL import Image

    try:
        if max_dim is not None and max_dim <= 0:
            max_dim = 1024
        if quality is not None and (quality < 1 or quality > 100):
            quality = 85

        auth_token = await webodm_auth_service()
        res = await webodm_task_download_service(ctx.project_name, ctx.task_name, ctx.asset_type, auth_token)

        file_bytes = res.content

        image = Image.open(io.BytesIO(file_bytes))

        # Original dimensions
        w_orig, h_orig = image.width, image.height

        # Calculate new dimensions
        if max_dim and (w_orig > max_dim or h_orig > max_dim):
            if w_orig > h_orig:
                w_new = max_dim
                h_new = int(h_orig * (max_dim / w_orig))
            else:
                h_new = max_dim
                w_new = int(w_orig * (max_dim / h_orig))
            
            # Resampling filter resolution for Pillow version compatibility
            resample_filter = getattr(Image, "Resampling", None)
            if resample_filter is not None:
                resample_mode = resample_filter.LANCZOS
            else:
                resample_mode = getattr(Image, "ANTIALIAS", Image.BICUBIC)
                
            image = image.resize((w_new, h_new), resample_mode)
        else:
            w_new, h_new = w_orig, h_orig

        if image.mode != "RGB":
            image = image.convert("RGB")

        jpeg_buffer = io.BytesIO()
        image.save(jpeg_buffer, format="JPEG", quality=quality)
        jpeg_buffer.seek(0)

        # Georeferencing metadata
        geo_headers = {}
        if ctx.asset_type.endswith((".tif", ".tiff")):
            try:
                import rasterio
                from rasterio.io import MemoryFile
                
                with MemoryFile(file_bytes) as memfile:
                    with memfile.open() as src:
                        bounds = src.bounds
                        crs_str = src.crs.to_string() if src.crs else "unknown"
                        
                        # Scale the original affine transform
                        t = src.transform
                        scale_x = w_orig / w_new if w_new > 0 else 1.0
                        scale_y = h_orig / h_new if h_new > 0 else 1.0
                        
                        new_transform_a = t.a * scale_x
                        new_transform_b = t.b * scale_y
                        new_transform_c = t.c
                        new_transform_d = t.d * scale_x
                        new_transform_e = t.e * scale_y
                        new_transform_f = t.f
                        
                        geo_headers = {
                            "X-Width": str(w_new),
                            "X-Height": str(h_new),
                            "X-Original-Width": str(w_orig),
                            "X-Original-Height": str(h_orig),
                            "X-CRS": crs_str,
                            "X-Bounds": f"{bounds.left},{bounds.bottom},{bounds.right},{bounds.top}",
                            "X-Transform": f"{new_transform_a},{new_transform_b},{new_transform_c},{new_transform_d},{new_transform_e},{new_transform_f}",
                        }
            except Exception as geo_err:
                print(f"Error reading GeoTIFF metadata: {geo_err}")

        headers = {
            "Content-Disposition": f"inline; filename={ctx.asset_type.split('.')[0]}.jpg"
        }
        headers.update(geo_headers)
        if geo_headers:
            headers["Access-Control-Expose-Headers"] = ", ".join(geo_headers.keys())

        return StreamingResponse(
            jpeg_buffer,
            media_type="image/jpeg",
            headers=headers,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
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


async def webodm_task_stream(project_name: str, task_id: str) -> StreamingResponse:
    """
    SSE endpoint that polls WebODM for a single task's live progress and
    pushes updates to the client until the task finishes or times out.

    Connect with EventSource in JS:
        const es = new EventSource('/webodm/projects/{project_name}/tasks/{task_id}/stream')
        es.onmessage = e => console.log(JSON.parse(e.data))
    """
    return StreamingResponse(
        _stream_webodm_task_progress(project_name, task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def webodm_task_get_dtm(
    project_name: str,
    task_name: str,
    max_resolution: int = 100,
    x_crs: Optional[str] = None,
    x_bounds: Optional[str] = None,
    x_transform: Optional[str] = None,
) -> webodm_dtm_response:
    import requests as _requests
    try:
        auth_token = await webodm_auth_service()
        points = await webodm_task_get_dtm_service(
            project_name=project_name,
            task_name=task_name,
            token=auth_token,
            max_resolution=max_resolution,
            x_crs=x_crs,
            x_bounds=x_bounds,
            x_transform=x_transform,
        )
        return webodm_dtm_response(points=points)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except _requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"DTM asset (dtm.tif) not found for task '{task_name}' in project '{project_name}'."
            )
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

