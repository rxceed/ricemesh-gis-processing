# src/server/routers/job_log_route.py
from fastapi import APIRouter

from server.schemas.job_log_schema import (
    jobLogListResponse as _jobLogListResponse,
    jobLogSingleResponse as _jobLogSingleResponse,
)
from server.controllers.job_log_controller import (
    get_all_job_logs    as _get_all_job_logs,
    get_job_logs_by_task as _get_job_logs_by_task,
    get_job_log_by_id   as _get_job_log_by_id,
)

job_log_router = APIRouter(prefix="/api/job-logs", tags=["Job Logs"])


@job_log_router.get("", status_code=200, response_model=_jobLogListResponse)
async def list_all_job_logs():
    """List all currently active worker job logs across all task types."""
    return await _get_all_job_logs()


@job_log_router.get("/task/{task}", status_code=200, response_model=_jobLogListResponse)
async def list_job_logs_by_task(task: str):
    """List active job logs filtered by task function name (e.g. upload_video, parse_video)."""
    return await _get_job_logs_by_task(task)


@job_log_router.get("/{job_id}", status_code=200, response_model=_jobLogSingleResponse)
async def get_job_log(job_id: str):
    """Get a single active job log by its arq job_id. Returns 404 if the job is not active."""
    return await _get_job_log_by_id(job_id)
