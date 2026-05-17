from beanie import Document, Indexed
from datetime import datetime
from typing import Annotated, Optional
from pydantic import Field
from pymongo import IndexModel, ASCENDING

class WebODMTask(Document):
    webodm_task_id: Annotated[str, Indexed(unique=True)] = Field(..., alias="webodmTaskId")
    webodm_project_id: int = Field(..., alias="webodmProjectId")
    owner_id: int = Field(..., alias="ownerId")
    project_name: str = Field(..., alias="projectName")
    task_name: str = Field(..., alias="taskName")
    status: str = "queued"
    is_processed: bool = Field(False, alias="isProcessed")
    created_at: datetime = Field(default_factory=datetime.now, alias="createdAt")
    
    class Settings:
        name = "webodm_tasks"
        indexes = [
            IndexModel([("webodmTaskId", ASCENDING), ("ownerId", ASCENDING)]),
            IndexModel([("webodmProjectId", ASCENDING)]),
            IndexModel([("isProcessed", ASCENDING)]),
        ]

    model_config = {"populate_by_name": True}
