from pydantic import BaseModel
from typing import Optional

class processed_map_download_model(BaseModel):
    project_name: str
    task_name: str
    owner_id: str
    asset_type: str
