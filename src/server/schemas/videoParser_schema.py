from pydantic import BaseModel

class parserBase(BaseModel):
    owner_id: int
    frame_interval: int = 1
    start: float = 0
    end: float | None = None