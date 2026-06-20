from beanie import Document, Indexed
from typing import List, Annotated
from pydantic import Field
from pydantic_mongo import PydanticObjectId
from pymongo import IndexModel, ASCENDING

class WebODMAsset(Document):
    gridfs_file_id: Annotated[PydanticObjectId, Indexed(unique=True)] = Field(..., alias="gridfsFileId")
    owner_id: str = Field(..., alias="ownerId")
    project_name: str = Field(..., alias="projectName")
    project_id: int = Field(..., alias="projectId")
    task_name: str = Field(..., alias="taskName")
    task_id: str = Field(..., alias="taskId")
    asset_type: str = Field(..., alias="assetType")  # 'orthophoto' or 'dtm'
    file_size_bytes: int = Field(..., alias="fileSizeBytes")
    resolution: List[int] = Field(..., description="[width, height]")  # [width, height]
    
    class Settings:
        name = "webodm_assets"
        indexes = [
            IndexModel([("gridfsFileId", ASCENDING), ("ownerId", ASCENDING)]),
            IndexModel([("projectId", ASCENDING), ("taskId", ASCENDING)]),
            IndexModel([("ownerId", ASCENDING), ("projectId", ASCENDING), ("taskId", ASCENDING), ("assetType", ASCENDING)]),
        ]

    model_config = {"populate_by_name": True}
