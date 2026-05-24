from pydantic import BaseModel
from typing import List, Optional, Any


# ── Request models ────────────────────────────────────────────────────────────

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


# ── Shared sub-models ─────────────────────────────────────────────────────────

class webodm_task_option(BaseModel):
    name: str
    value: Any

class webodm_task_model(BaseModel):
    """Represents a single WebODM task object."""
    id: int
    project: int
    processing_node: Optional[int] = None
    processing_node_name: Optional[str] = None
    images_count: int
    uuid: str
    name: Optional[str] = None
    processing_time: Optional[int] = None  # milliseconds, -1 if not available
    status: Optional[int] = None           # 10=Queued, 20=Running, 30=Completed, 40=Failed
    last_error: Optional[str] = None
    options: List[webodm_task_option] = []
    available_assets: List[str] = []
    created_at: str
    upload_progress: Optional[float] = None
    running_progress: Optional[float] = None
    auto_processing_node: Optional[bool] = None

class webodm_project_model(BaseModel):
    """Represents a single WebODM project object."""
    id: int
    name: str
    description: Optional[str] = None
    created_at: str
    tasks: List[int] = []
    permissions: List[str] = []
    public: Optional[bool] = None
    public_edit: Optional[bool] = None


# ── Response models ───────────────────────────────────────────────────────────

class webodm_auth_response(BaseModel):
    token: str

class webodm_project_list_response(BaseModel):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[webodm_project_model]

class webodm_project_create_response(BaseModel):
    message: str
    project: webodm_project_model

class webodm_project_update_response(BaseModel):
    message: str
    project: webodm_project_model

class webodm_delete_response(BaseModel):
    status: str

class webodm_task_create_response(BaseModel):
    message: str
    task: webodm_task_model

class webodm_task_list_response(BaseModel):
    """
    WebODM task list endpoint returns a plain list (not paginated).
    """
    results: List[webodm_task_model]

class webodm_task_cancel_response(BaseModel):
    status: str

class webodm_asset_delete_response(BaseModel):
    status: str
    message: str