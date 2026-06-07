# src/db/models/job_log.py
from beanie import Document
from datetime import datetime
from typing import Any, Optional
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class JobLog(Document):
    """Temporary log for an active arq worker job. Deleted once the task completes."""

    job_id: str = Field(..., alias="jobId")
    task: str = Field(..., description="Arq task function name, e.g. 'upload_video'")
    started_at: datetime = Field(default_factory=datetime.now, alias="startedAt")

    # Arbitrary task-specific payload (the args passed to the worker function).
    # Stored as a plain dict so any task can log whatever makes sense.
    job_args: dict[str, Any] = Field(default_factory=dict, alias="jobArgs")

    class Settings:
        name = "job_logs"
        indexes = [
            IndexModel([("jobId", ASCENDING)], unique=True),
            IndexModel([("task", ASCENDING)]),
        ]

    model_config = {"populate_by_name": True}
