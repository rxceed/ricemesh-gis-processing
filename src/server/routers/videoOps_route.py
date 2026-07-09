# src/server/routers/videoOps_route.py
from fastapi import APIRouter, File, Form, UploadFile, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Annotated, Optional, List

from server.schemas.videoOps_schema import (
    videoOpsParse as _videoOpsParse, 
    videoOpsBase as _videoOpsBase, 
    videoOpsWebodmTask as _videoOpsWebodmTask, 
    videoOpsResponseBase as _videoOpsResponseBase, 
    videoOpsArqWorkerResponse as _videoOpsArqWorkerResponse,
    videoOpsGetVidResponse as _videoOpsGetVidResponse,
    parsedImageListResponse as _parsedImageListResponse,
    parsedImageUploadResponse as _parsedImageUploadResponse)
from server.controllers.videoOps_controller import (
    video_upload      as _video_upload,
    video_parser      as _video_parser,
    get_video         as _get_video,
    video_webodm      as _video_webodm,
    get_job_status    as _get_job_status,
    job_event_stream  as _job_event_stream,
    video_delete      as _video_delete,
    parsed_image_delete as _parsed_image_delete,
    get_parsed_images as _get_parsed_images,
    video_update_srt  as _video_update_srt,
    upload_parsed_images as _upload_parsed_images,
)

videoOps_router = APIRouter(prefix="/api/video-ops", tags=["Video Operations"])


@videoOps_router.post("/upload", status_code=202, response_model=_videoOpsArqWorkerResponse)
async def upload(
    req: Request,
    owner_id: Annotated[str, Form(...)],
    file: UploadFile = File(...),
    srt_file: Optional[UploadFile] = File(None),
):
    """
    Save upload to disk and enqueue GridFS upload task.
    Returns 202 immediately with a job_id to track progress.
    """
    ctx = _videoOpsBase(owner_id=owner_id)
    return await _video_upload(req=req, ctx=ctx, file=file, srt_file=srt_file)


@videoOps_router.post("/parse", status_code=202, response_model=_videoOpsArqWorkerResponse)
async def parse(
    req: Request,
    owner_id: Annotated[str, Form(...)],
    filename: Annotated[str, Form(...)],
    frame_interval: Annotated[int, Form()] = 1,
    start: Annotated[float, Form()] = 0.0,
    end: Annotated[Optional[float], Form()] = None,
    srt_file: Optional[UploadFile] = File(None),
):
    """
    Enqueue frame extraction task.
    Returns 202 immediately with a job_id to track progress.
    """
    srt_content = None
    if srt_file:
        srt_bytes = await srt_file.read()
        srt_content = srt_bytes.decode("utf-8", errors="ignore")
    ctx = _videoOpsParse(
        owner_id=owner_id,
        filename=filename,
        frame_interval=frame_interval,
        start=start,
        end=end,
        srt_content=srt_content,
    )
    return await _video_parser(req=req, ctx=ctx)


@videoOps_router.post("/webodm", status_code=202, response_model=_videoOpsArqWorkerResponse)
async def webodm(req: Request, webodm: _videoOpsWebodmTask):
    """
    Enqueue WebODM processing task.
    Returns 202 immediately with a job_id to track progress.
    """
    return await _video_webodm(req=req, ctx=webodm)


@videoOps_router.get("/jobs/{job_id}", status_code=200)
async def job_status(job_id: str, req: Request):
    """
    Polling endpoint — current snapshot of a job's state and progress.
    """
    return await _get_job_status(job_id, req.state.redis)


@videoOps_router.get("/jobs/{job_id}/stream", status_code=200)
async def job_stream(job_id: str, req: Request):
    """
    Server-Sent Events stream — pushes progress events every second
    until the job completes or times out.

    Connect with EventSource in JS:
        const es = new EventSource('/api/video-ops/jobs/{job_id}/stream')
        es.onmessage = e => console.log(JSON.parse(e.data))
    """
    return StreamingResponse(
        _job_event_stream(job_id, req.state.redis),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
            "X-Accel-Buffering": "no",   # disables nginx response buffering
        },
    )


@videoOps_router.get("/get/{owner_id}", status_code=200, response_model=_videoOpsGetVidResponse)
async def get(req: Request, owner_id: str):
    ctx = _videoOpsBase(owner_id=owner_id)
    return await _get_video(req=req, ctx=ctx)


@videoOps_router.delete("/videos/{video_id}", status_code=200, response_model=_videoOpsResponseBase)
async def delete_video(req: Request, video_id: str, owner_id: str):
    return await _video_delete(req=req, video_id=video_id, owner_id=owner_id)


@videoOps_router.delete("/parsed/{parsed_id}", status_code=200, response_model=_videoOpsResponseBase)
async def delete_parsed_image(req: Request, parsed_id: str, owner_id: str):
    return await _parsed_image_delete(req=req, parsed_id=parsed_id, owner_id=owner_id)


@videoOps_router.get("/parsed", status_code=200, response_model=_parsedImageListResponse)
async def list_parsed_images(
    owner_id: str | None = None,
    filename: str | None = None,
):
    """List parsed images, optionally filtered by owner_id and/or filename query params."""
    return await _get_parsed_images(owner_id=owner_id, filename=filename)


@videoOps_router.put("/videos/{video_id}/srt", status_code=200, response_model=_videoOpsResponseBase)
async def update_srt(
    req: Request,
    video_id: str,
    owner_id: Annotated[str, Form(...)],
    srt_file: UploadFile = File(...),
):
    """Edit and replace the .SRT file content in a VideoUpload document."""
    srt_bytes = await srt_file.read()
    srt_content = srt_bytes.decode("utf-8", errors="ignore")
    return await _video_update_srt(req=req, video_id=video_id, owner_id=owner_id, srt_content=srt_content)


@videoOps_router.post("/parsed/upload", status_code=201, response_model=_parsedImageUploadResponse)
async def upload_parsed_images(
    req: Request,
    owner_id: Annotated[str, Form(...)],
    filename: Annotated[str, Form(...)],
    files: List[UploadFile] = File(...),
):
    """
    Directly upload multiple parsed image files, saving them to GridFS and
    linking them in a ParsedImage document.
    """
    return await _upload_parsed_images(
        req=req,
        owner_id=owner_id,
        filename=filename,
        files=files,
    )