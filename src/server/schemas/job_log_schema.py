# src/server/schemas/job_log_schema.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, List, Optional


class jobLogResponse(BaseModel):
    job_id: str = Field(..., alias="jobId")
    task: str
    started_at: datetime = Field(..., alias="startedAt")
    job_args: dict[str, Any] = Field(..., alias="jobArgs")

    model_config = {"populate_by_name": True, "from_attributes": True}


class jobLogListResponse(BaseModel):
    status: str
    logs: List[jobLogResponse]


class jobLogSingleResponse(BaseModel):
    status: str
    log: jobLogResponse
