# src/server/controllers/videoOps_controller.py
import asyncio
import json

from arq.jobs import Job, JobStatus
from fastapi import File, UploadFile, HTTPException, status, Request
from server.services.webodm_service import (
    webodm_auth_service as _webodm_auth_service,
    webodm_project_get_service as _webodm_project_get_service,
    webodm_task_progress_service as _webodm_task_progress_service,
)

from server.schemas.videoOps_schema import (
    videoOpsParse as _videoOpsParse, 
    videoOpsBase as _videoOpsBase, 
    videoOpsWebodmTask as _videoOpsWebodmTask, 
    videoOpsResponseBase as _videoOpsResponseBase, 
    videoOpsArqWorkerResponse as _videoOpsArqWorkerResponse,
    videoOpsGetVidResponse as _videoOpsGetVidResponse,
    parsedImageListResponse as _parsedImageListResponse)
from server.services.videoOps_service import (
    get_video_service,
    video_parser_service,
    video_upload_service,
    video_webodm_service,
    video_delete_service,
    parsed_image_delete_service,
    get_parsed_images_service,
)


# ── Existing handlers (unchanged logic, redis thread through) ─────────────

async def video_upload(req: Request, ctx: _videoOpsBase, file: UploadFile = File(...)):
    try:
        # Fast extension check (case-insensitive for the user)
        if not file.filename.lower().endswith((".mp4",)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .mp4 files are accepted",
            )
        
        # Service handles magic number validation and extension normalization
        res = await video_upload_service(ctx, file, redis=req.state.redis)
        return _videoOpsArqWorkerResponse(job_id=res["job_id"],
                                            status=res["status"],
                                            message=res["message"])
        
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


async def video_parser(req: Request, ctx: _videoOpsParse):
    try:
        res = await video_parser_service(ctx, redis=req.state.redis)
        return _videoOpsArqWorkerResponse(job_id=res["job_id"],
                                            status=res["status"],
                                            message=res["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_video(req: Request, ctx: _videoOpsBase):
    try:
        res = await get_video_service(ctx)
        return _videoOpsGetVidResponse(status=res["status"], video=res["video"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def video_webodm(req: Request, ctx: _videoOpsWebodmTask):
    try:
        res = await video_webodm_service(ctx, redis=req.state.redis)
        return _videoOpsArqWorkerResponse(job_id=res["job_id"],
                                            status=res["status"],
                                            message=res["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def video_delete(req: Request, video_id: str, owner_id: str):
    try:
        res = await video_delete_service(video_id, owner_id, db=req.app.state.db)
        return _videoOpsResponseBase(status=res["status"], message=res["message"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def parsed_image_delete(req: Request, parsed_id: str, owner_id: str):
    try:
        res = await parsed_image_delete_service(parsed_id, owner_id, db=req.app.state.db)
        return _videoOpsResponseBase(status=res["status"], message=res["message"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_parsed_images(owner_id: str | None, filename: str | None):
    try:
        res = await get_parsed_images_service(owner_id=owner_id, filename=filename)
        return _parsedImageListResponse(status=res["status"], images=res["images"])
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

    try:
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
                # Signal client to close the EventSource connection
                yield f"event: done\ndata: close\n\n"
                return

            if status_val == JobStatus.not_found:
                payload["error"] = "Job not found or result expired"
                yield f"data: {json.dumps(payload)}\n\n"
                yield f"event: done\ndata: close\n\n"
                return

            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        # Timeout reached
        yield f'data: {json.dumps({"job_id": job_id, "status": "timeout"})}\n\n'
        yield f"event: done\ndata: close\n\n"

    except asyncio.CancelledError:
        # Client disconnected — stop polling gracefully
        return


# ── SSE helper: stream progress for a single WebODM task ──────────────────

async def stream_webodm_task_progress(
    project_name: str,
    task_id: str,
    poll_interval: float = 3.0,
    timeout_sec: float = 7_200,
):
    """
    Async generator that polls WebODM for a single task's live status and
    yields SSE-formatted events until the task reaches a terminal state or
    the timeout is reached.

    Resolves project_name to a WebODM project_id before streaming.

    WebODM status codes:
        10  Queued
        20  Running
        30  Failed
        40  Completed
        50  Canceled

    Yields strings in SSE wire format:  data: <json>\n\n
    """
    _TERMINAL = {30, 40, 50}

    elapsed = 0.0

    # Authenticate
    try:
        token = await _webodm_auth_service()
    except Exception as exc:
        payload = {"error": f"WebODM authentication failed: {exc}"}
        yield f"data: {json.dumps(payload)}\n\n"
        yield f"event: done\ndata: close\n\n"
        return

    # Resolve project_name → project_id
    try:
        project_list = await _webodm_project_get_service(token, name=project_name)
        if isinstance(project_list, dict):
            results = project_list.get("results", [])
        elif isinstance(project_list, list):
            results = project_list
        else:
            results = []

        project = next((p for p in results if p.get("name") == project_name), None)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")

        project_id = project["id"]
    except Exception as exc:
        payload = {"error": f"Failed to resolve project: {exc}"}
        yield f"data: {json.dumps(payload)}\n\n"
        yield f"event: done\ndata: close\n\n"
        return

    try:
        while elapsed < timeout_sec:
            try:
                progress = await _webodm_task_progress_service(project_id, task_id, token)
            except Exception as exc:
                payload = {"error": f"Failed to fetch task status: {exc}"}
                yield f"data: {json.dumps(payload)}\n\n"
                yield f"event: done\ndata: close\n\n"
                return

            payload = {
                "project_name": project_name,
                "project_id":   project_id,
                "task_id":      task_id,
                **progress,
            }

            yield f"data: {json.dumps(payload)}\n\n"

            # Stop streaming when task has reached a terminal state
            if progress["status_code"] in _TERMINAL:
                yield f"event: done\ndata: close\n\n"
                return

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            # Re-authenticate periodically to avoid token expiry on long tasks
            if elapsed % 1800 < poll_interval:
                try:
                    token = await _webodm_auth_service()
                except Exception:
                    pass  # keep using the old token; next iteration will catch auth errors

        # Timeout reached
        yield f'data: {json.dumps({"task_id": task_id, "status": "timeout"})}\n\n'
        yield f"event: done\ndata: close\n\n"

    except asyncio.CancelledError:
        # Client disconnected — stop polling gracefully
        return

