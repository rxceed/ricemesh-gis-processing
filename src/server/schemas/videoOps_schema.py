from pydantic import BaseModel
from typing import Optional, List

class videoOpsBase(BaseModel):
    owner_id: int

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