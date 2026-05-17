from typing import Optional, List
from beanie import Document, Indexed
from pydantic import BaseModel, Field
from pymongo import IndexModel, ASCENDING
from pydantic_mongo import PydanticObjectId

class frames(BaseModel):
    gridfs_file_id: PydanticObjectId = Field(..., alias="gridfsFileId")
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
