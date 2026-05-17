# src/server/controllers/videoOps_controller.py
import asyncio
import json

from arq.jobs import Job, JobStatus
from fastapi import File, UploadFile, HTTPException, status, Request

from server.schemas.videoOps_schema import videoOpsParse, videoOpsBase, videoOpsWebodmTask
from server.services.videoOps_service import (
    get_video_service,
    video_parser_service,
    video_upload_service,
    video_webodm_service,
    video_delete_service,
    parsed_image_delete_service
)


# ── Existing handlers (unchanged logic, redis thread through) ─────────────

async def video_upload(req: Request, ctx: videoOpsBase, file: UploadFile = File(...)):
    try:
        # Fast extension check (case-insensitive for the user)
        if not file.filename.lower().endswith((".mp4",)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .mp4 files are accepted",
            )
        
        # Service handles magic number validation and extension normalization
        return await video_upload_service(ctx, file, redis=req.state.redis)
        
    except ValueError as e:
        # Catch validation errors from the service
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def video_parser(req: Request, ctx: videoOpsParse):
    try:
        return await video_parser_service(ctx, redis=req.state.redis)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_video(req: Request, ctx: videoOpsBase):
    try:
        return await get_video_service(ctx)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def video_webodm(req: Request, ctx: videoOpsWebodmTask):
    try:
        return await video_webodm_service(ctx, redis=req.state.redis)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def video_delete(req: Request, video_id: str, owner_id: int):
    try:
        return await video_delete_service(video_id, owner_id, db=req.app.state.db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def parsed_image_delete(req: Request, parsed_id: str, owner_id: int):
    try:
        return await parsed_image_delete_service(parsed_id, owner_id, db=req.app.state.db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── New: job status + SSE stream ──────────────────────────────────────────

async def get_job_status(job_id: str, redis) -> dict:
    """
    Snapshot of a job's current state. For clients that prefer polling
    over a persistent SSE connection.
    """
    job    = Job(job_id, redis)
    status_val = await job.status()

    payload: dict = {"job_id": job_id, "status": status_val.value}

    # Merge in the detailed progress blob if it exists
    raw = await redis.get(f"job_progress:{job_id}")
    if raw:
        payload.update(json.loads(raw))

    # For completed jobs, attach the final result or error
    if status_val == JobStatus.complete:
        try:
            payload["result"] = await job.result(timeout=1)
        except Exception as exc:
            payload["error"] = str(exc)

    return payload


async def job_event_stream(job_id: str, redis):
    """
    Async generator for the SSE endpoint.

    Yields one JSON event per second. Exits when the job reaches a
    terminal state (complete) or the 2-hour timeout is hit.

    SSE format:
        data: {"job_id": "...", "status": "in_progress", ...}\n\n
    """
    POLL_INTERVAL = 1.0
    TIMEOUT_SEC   = 7_200

    elapsed = 0.0

    while elapsed < TIMEOUT_SEC:
        job        = Job(job_id, redis)
        status_val = await job.status()

        payload: dict = {"job_id": job_id, "status": status_val.value}

        # Merge detailed progress (stage, percent, message, etc.)
        raw = await redis.get(f"job_progress:{job_id}")
        if raw:
            payload.update(json.loads(raw))

        if status_val == JobStatus.complete:
            try:
                payload["result"]  = await job.result(timeout=1)
                payload["success"] = True
            except Exception as exc:
                payload["error"]   = str(exc)
                payload["success"] = False
            yield f"data: {json.dumps(payload)}\n\n"
            return  # terminal — close the stream

        if status_val == JobStatus.not_found:
            payload["error"] = "Job not found or result expired"
            yield f"data: {json.dumps(payload)}\n\n"
            return

        yield f"data: {json.dumps(payload)}\n\n"
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    yield f'data: {json.dumps({"job_id": job_id, "status": "timeout"})}\n\n'
