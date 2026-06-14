from pydantic import BaseModel, Field
from typing import Optional, List
from pydantic_mongo import PydanticObjectId
from db.models.common import video_resolution

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

class videoOpsVideoResponse(BaseModel):
    id: PydanticObjectId = Field(..., alias="_id")
    gridfs_file_id: PydanticObjectId = Field(..., alias="gridfsFileId")
    owner_id: str = Field(..., alias="ownerId")
    filename: str
    size_bytes: int = Field(..., alias="sizeBytes")
    mime_type: str = Field(..., alias="mimeType")
    duration_sec: Optional[float] = Field(None, alias="durationSec")
    fps: Optional[float] = None
    resolution: Optional[video_resolution] = None
    codec: Optional[str] = None

    model_config = {"populate_by_name": True, "from_attributes": True}

class videoOpsGetVidResponse(videoOpsResponseBase):
    video: List[videoOpsVideoResponse]


class framesResponse(BaseModel):
    gridfs_file_id: PydanticObjectId = Field(..., alias="gridfsFileId")
    frame_index: int = Field(..., alias="frameIndex")

    model_config = {"populate_by_name": True, "from_attributes": True}


class parsedImageResponse(BaseModel):
    owner_id: str = Field(..., alias="ownerId")
    filename: str
    image_frames: List[framesResponse] = Field(..., alias="imageFrames")

    model_config = {"populate_by_name": True, "from_attributes": True}


class parsedImageListResponse(videoOpsResponseBase):
    images: List[parsedImageResponse]