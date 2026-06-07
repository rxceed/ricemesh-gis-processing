# src/server/services/job_log_service.py
from db.models import JobLog


async def get_all_job_logs_service() -> dict:
    """Return all active job log documents."""
    logs = await JobLog.find_all().to_list()
    return {"status": "OK", "logs": logs}


async def get_job_logs_by_task_service(task: str) -> dict:
    """Return all active job log documents for a given task function name."""
    logs = await JobLog.find(JobLog.task == task).to_list()
    return {"status": "OK", "logs": logs}


async def get_job_log_by_id_service(job_id: str) -> dict:
    """Return a single job log document by arq job_id. Raises ValueError if not found."""
    log = await JobLog.find_one(JobLog.job_id == job_id)
    if not log:
        raise ValueError(f"No active job log found for job_id={job_id}")
    return {"status": "OK", "log": log}
