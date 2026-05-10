# db/models/video_capture.py
from typing import Optional
from beanie import Document
from pydantic import Field
from pydantic_mongo import PydanticObjectId
from pymongo import IndexModel, ASCENDING
from db.models.common import video_resolution

class VideoUpload(Document):
    gridfs_file_id: PydanticObjectId  = Field(..., alias="gridfsFileId")
    owner_id: int = Field(..., alias="ownerId")
    filename: str
    size_bytes: int = Field(..., alias="sizeBytes")
    mime_type: str = Field("video/mp4", alias="mimeType")
    duration_sec: Optional[float] = Field(None, alias="durationSec")
    fps: Optional[float] = None
    resolution: Optional[video_resolution] = None
    codec: Optional[str] = None

    class Settings:
        name = "video_uploads"
        indexes = [
            IndexModel([("gridfsFileId", ASCENDING), ("ownerId", ASCENDING)]),
        ]

    model_config = {"populate_by_name": True}