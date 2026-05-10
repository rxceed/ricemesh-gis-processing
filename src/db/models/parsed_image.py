from typing import Optional, List
from beanie import Document, Link
from pydantic import Field, BaseModel
from pymongo import IndexModel, ASCENDING
from db.models.common import video_resolution
from db.models.video_upload import VideoUpload

class frames(BaseModel):
    image_data: bytes = Field(..., alias="imageData")
    frame_index: int = Field(..., alias="frameIndex")
    timestamp_ms: int = Field(..., alias="timestampMs")
    resolution: video_resolution
    size_bytes: int = Field(..., alias="sizeBytes")

class ParsedImage(Document):
    source_video: Link[VideoUpload] = Field(..., alias="sourceVideo")
    image_frames: List[frames] = Field(..., alias="imageFrames")

    class Settings:
        name = "parsed_images"
        indexes = [
            # Primary query: all frames for a session in temporal order
            IndexModel([("sourceVideo", ASCENDING), ("imageFrames.frameIndex", ASCENDING)])
        ]

    model_config = {"populate_by_name": True}