from typing import Optional, List, Annotated
from bunnet import Document, Indexed
from pydantic import Field, BaseModel
from pymongo import IndexModel, ASCENDING
from pydantic_mongo import PydanticObjectId
from db.models.common import video_resolution

class frames(BaseModel):
    image_data: bytes = Field(..., alias="imageData")
    frame_index: int = Field(..., alias="frameIndex")

class ParsedImage(Document):
    owner_id: int = Field(..., alias="ownerId")
    filename: str
    image_frames: List[frames] = Field(..., alias="imageFrames")

    class Settings:
        name = "parsed_images"
        indexes = [
            # Primary query: all frames for a session in temporal order
            IndexModel([("sourceVideo", ASCENDING), ("imageFrames.frameIndex", ASCENDING)])
        ]
    model_config = {"populate_by_name": True}

class VideoUpload(Document):
    gridfs_file_id: Annotated[PydanticObjectId, Indexed(unique=True)]  = Field(..., alias="gridfsFileId")
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