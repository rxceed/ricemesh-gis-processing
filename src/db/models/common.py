from pydantic import BaseModel
from bson import ObjectId
from typing import Annotated, Any
from pydantic import BaseModel, BeforeValidator, PlainSerializer

class video_resolution(BaseModel):
    width: int
    height: int

def validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")

PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(lambda x: str(x), return_type=str),
]