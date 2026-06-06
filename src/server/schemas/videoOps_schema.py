from pydantic import BaseModel, Field
from typing import Optional, List
from db.models.video_upload import VideoUpload

class videoOpsBase(BaseModel):
    owner_id: str = Field(..., description="User ID of the video owner")

class videoOpsParse(videoOpsBase):
    filename: str
    frame_interval: int = 1
    start: float = 0
    end: float | None = None

class videoOpsWebodmTask(videoOpsBase):
    filename: str
    project_name: str
    task_name: Optional[str] = None
    options: Optional[List[dict]] = None

class videoOpsResponseBase(BaseModel):
    status: str
    message: Optional[str] = None

class videoOpsArqWorkerResponse(videoOpsResponseBase):
    job_id: str

class videoOpsGetVidResponse(videoOpsResponseBase):
    video: List[VideoUpload]