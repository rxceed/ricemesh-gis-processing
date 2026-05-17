# src/server/routers/videoOps_route.py
from fastapi import APIRouter, File, UploadFile, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Annotated

from server.schemas.videoOps_schema import videoOpsBase, videoOpsParse, videoOpsWebodmTask
from server.controllers.videoOps_controller import (
    video_upload      as _video_upload,
    video_parser      as _video_parser,
    get_video         as _get_video,
    video_webodm      as _video_webodm,
    get_job_status    as _get_job_status,
    job_event_stream  as _job_event_stream,
    video_delete      as _video_delete,
    parsed_image_delete as _parsed_image_delete,
)

videoOps_router = APIRouter(prefix="/api/video-ops", tags=["Video Operations"])


@videoOps_router.post("/upload", status_code=202)
async def upload(
    req: Request,
    upload: Annotated[videoOpsBase, Depends()],
    file: UploadFile = File(...),
):
    """
    Save upload to disk and enqueue GridFS upload task.
    Returns 202 immediately with a job_id to track progress.
    """
    return await _video_upload(req=req, ctx=upload, file=file)


@videoOps_router.post("/parse", status_code=202)
async def parse(req: Request, parse: Annotated[videoOpsParse, Depends()]):
    """
    Enqueue frame extraction task.
    Returns 202 immediately with a job_id to track progress.
    """
    return await _video_parser(req=req, ctx=parse)


@videoOps_router.post("/webodm", status_code=202)
async def webodm(req: Request, webodm: Annotated[videoOpsWebodmTask, Depends()]):
    """
    Enqueue WebODM processing task.
    Returns 202 immediately with a job_id to track progress.
    """
    return await _video_webodm(req=req, ctx=webodm)


@videoOps_router.get("/jobs/{job_id}")
async def job_status(job_id: str, req: Request):
    """
    Polling endpoint — current snapshot of a job's state and progress.
    """
    return await _get_job_status(job_id, req.state.redis)


@videoOps_router.get("/jobs/{job_id}/stream")
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


@videoOps_router.post("/get", status_code=200)
async def get(req: Request, get: Annotated[videoOpsBase, Depends()]):
    return await _get_video(req=req, ctx=get)


@videoOps_router.delete("/videos/{video_id}")
async def delete_video(req: Request, video_id: str, owner_id: int):
    return await _video_delete(req=req, video_id=video_id, owner_id=owner_id)


@videoOps_router.delete("/parsed/{parsed_id}")
async def delete_parsed_image(req: Request, parsed_id: str, owner_id: int):
    return await _parsed_image_delete(req=req, parsed_id=parsed_id, owner_id=owner_id)