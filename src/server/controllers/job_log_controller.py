# src/server/controllers/job_log_controller.py
from fastapi import HTTPException, status

from server.schemas.job_log_schema import (
    jobLogListResponse as _jobLogListResponse,
    jobLogSingleResponse as _jobLogSingleResponse,
)
from server.services.job_log_service import (
    get_all_job_logs_service,
    get_job_logs_by_task_service,
    get_job_log_by_id_service,
)


async def get_all_job_logs():
    try:
        res = await get_all_job_logs_service()
        return _jobLogListResponse(status=res["status"], logs=res["logs"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_job_logs_by_task(task: str):
    try:
        res = await get_job_logs_by_task_service(task)
        return _jobLogListResponse(status=res["status"], logs=res["logs"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_job_log_by_id(job_id: str):
    try:
        res = await get_job_log_by_id_service(job_id)
        return _jobLogSingleResponse(status=res["status"], log=res["log"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
