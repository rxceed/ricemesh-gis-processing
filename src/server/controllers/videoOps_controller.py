from server.schemas.videoOps_schema import videoOpsParse, videoOpsBase
from server.services.videoOps_service import get_video_service, video_parser_service, video_upload_service

from fastapi import File, UploadFile, HTTPException, status, Request

import asyncio
import json
from celery.result import AsyncResult
from celery_app.app import celery_app

async def video_upload(req: Request, ctx: videoOpsBase, file: UploadFile = File(...)):
    try:
        filename = file.filename
        file_format = filename.split(".")[1]
        if not(file_format == "mp4" or file_format == "MP4"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video format and extension must be in .mp4 or .MP4")
        res = await video_upload_service(ctx, file, db=req.state.db)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured during video upload: {res}")
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")

async def video_parser(req: Request, ctx: videoOpsParse):
    try:
        res = await video_parser_service(ctx, db=req.state.db)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured in response: {res}")
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")
    
async def get_video(req: Request, ctx: videoOpsBase):
    try:
        res = await get_video_service(ctx)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {res}")
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")

async def _poll_task_state(task_id: str) -> tuple[str, dict | None]:
    """
    Fetch Celery task state without blocking the event loop.

    AsyncResult.state and .info hit MongoDB synchronously. Running them
    in the default ThreadPoolExecutor moves that blocking call off the
    event loop thread, keeping FastAPI responsive to other requests
    while we wait for the DB round-trip.
    """
    loop   = asyncio.get_event_loop()
    result = AsyncResult(task_id, app=celery_app)

    state = await loop.run_in_executor(None, lambda: result.state)
    info  = await loop.run_in_executor(None, lambda: result.info)

    return state, info


async def get_task_status(task_id: str) -> dict:
    """
    Snapshot of current task state. Used for polling clients.
    GET /api/video-ops/tasks/{task_id}
    """
    state, info = await _poll_task_state(task_id)

    payload = {"task_id": task_id, "state": state}

    if state == "PROGRESS":
        payload.update(info or {})
    elif state == "SUCCESS":
        payload["result"] = info
    elif state == "FAILURE":
        # info is the exception instance when state is FAILURE
        payload["error"] = str(info)

    return payload


async def task_event_stream(task_id: str):
    """
    SSE generator for a Celery task.
    GET /api/video-ops/tasks/{task_id}/stream

    Yields SSE-formatted strings every second until the task reaches
    a terminal state (SUCCESS or FAILURE) or a timeout is exceeded.

    SSE wire format:
        data: {"task_id": "...", "state": "PROGRESS", ...}\n\n

    Why poll instead of Celery signals?
      Celery's task_success / task_failure signals fire inside the
      worker process — a different OS process from FastAPI. Bridging
      signals across processes requires a shared pub/sub channel
      (Redis Pub/Sub, RabbitMQ exchanges). We already poll MongoDB
      for AsyncResult.state, so polling every second is simpler and
      adds no new infrastructure. For 1-second granularity it's fine.
    """
    POLL_INTERVAL_SEC = 1.0
    TIMEOUT_SEC       = 7_200  # 2 hours — enough for any realistic video

    elapsed = 0.0

    while elapsed < TIMEOUT_SEC:
        state, info = await _poll_task_state(task_id)

        payload: dict = {"task_id": task_id, "state": state}

        if state == "PENDING":
            payload["message"] = "Task is queued, waiting for a worker"

        elif state == "STARTED":
            payload["message"] = "Worker picked up the task"

        elif state == "PROGRESS":
            # info is the meta dict passed to update_state()
            payload.update(info or {})

        elif state == "SUCCESS":
            payload["result"] = info
            # Terminal state — yield final event and close the stream
            yield f"data: {json.dumps(payload)}\n\n"
            return

        elif state == "FAILURE":
            payload["error"] = str(info)
            yield f"data: {json.dumps(payload)}\n\n"
            return

        yield f"data: {json.dumps(payload)}\n\n"

        await asyncio.sleep(POLL_INTERVAL_SEC)
        elapsed += POLL_INTERVAL_SEC

    # Timed out without reaching a terminal state
    yield f'data: {json.dumps({"task_id": task_id, "state": "TIMEOUT", "message": "Stream timed out"})}\n\n'