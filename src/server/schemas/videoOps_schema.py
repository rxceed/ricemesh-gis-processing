from pydantic import BaseModel, Field
from typing import Optional, List
from pydantic_mongo import PydanticObjectId
from db.models.video_upload import VideoUpload

class videoOpsBase(BaseModel):
    owner_id: str = Field(..., description="User ID of the video owner")

class videoOpsParse(videoOpsBase):
    filename: str
    frame_interval: int = 1
    start: float = 0
    end: float | None = None
    srt_content: Optional[str] = None

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


class framesResponse(BaseModel):
    gridfs_file_id: PydanticObjectId = Field(..., alias="gridfsFileId")
    frame_index: int = Field(..., alias="frameIndex")

    model_config = {"populate_by_name": True, "from_attributes": True}


class parsedImageResponse(BaseModel):
    owner_id: str = Field(..., alias="ownerId")
    filename: str
    image_frames: List[framesResponse] = Field(..., alias="imageFrames")
    geo_txt: Optional[str] = Field(None, alias="geoTxt")

    model_config = {"populate_by_name": True, "from_attributes": True}


class parsedImageListResponse(videoOpsResponseBase):
    images: List[parsedImageResponse]