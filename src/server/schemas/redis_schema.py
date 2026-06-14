# src/server/schemas/redis_schema.py
from pydantic import BaseModel, Field
from typing import Any, List

class redis_key_info(BaseModel):
    key: str = Field(..., description="The name of the Redis key")
    type: str = Field(..., description="The type of the Redis key (e.g. string, hash, list, set)")
    ttl: int = Field(..., description="The remaining time-to-live in seconds, -1 means no expiry, -2 means expired/not exist")

class redis_keys_response(BaseModel):
    status: str = Field(..., description="Status of the request")
    keys: List[redis_key_info] = Field(..., description="List of keys in Redis cache")

class redis_value_response(BaseModel):
    status: str = Field(..., description="Status of the request")
    key: str = Field(..., description="The Redis key name")
    type: str = Field(..., description="The type of the key")
    ttl: int = Field(..., description="The remaining time-to-live in seconds")
    value: Any = Field(..., description="The value stored in the key, formatted according to the type")
