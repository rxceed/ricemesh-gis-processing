from fastapi import APIRouter, File, UploadFile, Request, responses, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Annotated
from server.schemas.videoOps_schema import videoOpsBase, videoOpsParse
from server.controllers.videoOps_controller import (
    video_parser     as _video_parser,
    video_upload     as _video_upload,
    get_video        as _get_video,
    get_task_status  as _get_task_status,    # new
    task_event_stream as _task_event_stream, # new
)

videoOps_router = APIRouter(prefix="/api/video-ops")

@videoOps_router.post("/upload", status_code=201, response_class=responses.JSONResponse)
async def upload(req: Request, upload: Annotated[videoOpsBase, Depends()], file: UploadFile=File(...)):
    return await _video_upload(req=req, ctx=upload, file=file)

@videoOps_router.post("/parse", status_code=202, response_class=responses.JSONResponse)
async def parse(req: Request, parse: Annotated[videoOpsParse, Depends()]):
    """
    Enqueue a video parsing job. Returns immediately with a task_id.
    202 Accepted signals that the work has been accepted but not yet complete.
    """
    return await _video_parser(req=req, ctx=parse)


@videoOps_router.get("/tasks/{task_id}", response_class=JSONResponse)
async def task_status(task_id: str):
    """
    Polling endpoint — snapshot of task state at this moment.
    Useful for clients that can't maintain a persistent SSE connection.
    """
    return await _get_task_status(task_id)


@videoOps_router.get("/tasks/{task_id}/stream")
async def task_stream(task_id: str):
    """
    Server-Sent Events stream for real-time task progress.
    The client keeps this connection open; the server pushes JSON events
    every second until the task completes.

    Headers set here:
      Cache-Control: no-cache         — proxies must not buffer events
      X-Accel-Buffering: no           — disables nginx proxy buffering
      Connection: keep-alive          — explicit keep-alive for HTTP/1.1
    """
    return StreamingResponse(
        _task_event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "Connection":       "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@videoOps_router.post("/get", status_code=200, response_class=responses.JSONResponse)
async def get(req: Request, get: Annotated[videoOpsBase, Depends()]):
    return await _get_video(req=req, ctx=get)