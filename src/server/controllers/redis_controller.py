# src/server/controllers/redis_controller.py
from fastapi import HTTPException, status
from server.schemas.redis_schema import (
    redis_keys_response as _redis_keys_response,
    redis_value_response as _redis_value_response,
)
from server.services.redis_service import (
    get_redis_keys_service,
    get_redis_key_value_service,
)

async def get_redis_keys(redis, pattern: str = "*"):
    """
    Controller to handle fetching all matching keys from Redis.
    """
    try:
        res = await get_redis_keys_service(redis, pattern)
        return _redis_keys_response(status=res["status"], keys=res["keys"])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

async def get_redis_key_value(redis, key: str):
    """
    Controller to handle fetching the value of a specific key from Redis.
    """
    try:
        res = await get_redis_key_value_service(redis, key)
        return _redis_value_response(
            status=res["status"],
            key=res["key"],
            type=res["type"],
            ttl=res["ttl"],
            value=res["value"]
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
