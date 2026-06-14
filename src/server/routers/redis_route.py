# src/server/routers/redis_route.py
from fastapi import APIRouter, Request

from server.schemas.redis_schema import (
    redis_keys_response as _redis_keys_response,
    redis_value_response as _redis_value_response,
)
from server.controllers.redis_controller import (
    get_redis_keys as _get_redis_keys,
    get_redis_key_value as _get_redis_key_value,
)

redis_router = APIRouter(prefix="/api/debug/redis", tags=["Redis Debugging"])

@redis_router.get("/keys", status_code=200, response_model=_redis_keys_response)
async def list_keys(req: Request, pattern: str = "*"):
    """
    List keys stored in Redis cache matching the pattern.
    """
    return await _get_redis_keys(req.state.redis, pattern)

@redis_router.get("/keys/{key:path}", status_code=200, response_model=_redis_value_response)
async def get_key_value(req: Request, key: str):
    """
    Retrieve the value of a specific key stored in Redis cache.
    """
    return await _get_redis_key_value(req.state.redis, key)
