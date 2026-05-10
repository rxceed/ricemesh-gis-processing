from pydantic import BaseModel

class videoOpsBase(BaseModel):
    owner_id: int

class videoOpsParse(videoOpsBase):
    filename: str
    frame_interval: int = 1
    start: float = 0
    end: float | None = None