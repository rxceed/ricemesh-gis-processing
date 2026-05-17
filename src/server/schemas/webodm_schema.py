from pydantic import BaseModel
from typing import List, Optional

class webodm_auth_model(BaseModel):
    username: str
    password: str

class webodm_project_modelBase(BaseModel):
    project_name: str
    project_description: Optional[str] = None

class webodm_project_update_model(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class webodm_task_create_model(BaseModel):
    name: Optional[str] = None
    options: Optional[List[dict]] = None

class webodm_asset_download_model(BaseModel):
    project_name: str
    task_name: str
    asset_type: str