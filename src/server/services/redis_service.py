# src/server/services/redis_service.py
import json
from typing import Any

async def get_redis_keys_service(redis, pattern: str = "*") -> dict:
    """
    Retrieve all keys in Redis matching the given pattern,
    along with their type and TTL.
    """
    raw_keys = await redis.keys(pattern)
    keys = []
    
    for raw_key in raw_keys:
        key_str = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
        
        # Get type of the key
        type_bytes = await redis.type(key_str)
        type_str = type_bytes.decode("utf-8") if isinstance(type_bytes, bytes) else type_bytes
        
        # Get TTL of the key
        ttl = await redis.ttl(key_str)
        
        keys.append({
            "key": key_str,
            "type": type_str,
            "ttl": ttl
        })
        
    return {"status": "OK", "keys": keys}

async def get_redis_key_value_service(redis, key: str) -> dict:
    """
    Retrieve the value and metadata of a specific Redis key.
    Raises ValueError if the key does not exist.
    """
    type_bytes = await redis.type(key)
    type_str = type_bytes.decode("utf-8") if isinstance(type_bytes, bytes) else type_bytes
    
    if type_str == "none":
        raise ValueError(f"Key '{key}' does not exist in Redis cache.")
        
    ttl = await redis.ttl(key)
    value: Any = None
    
    # Handle retrieving and parsing values based on the Redis data type
    if type_str == "string":
        raw_val = await redis.get(key)
        if raw_val is not None:
            val_str = raw_val.decode("utf-8") if isinstance(raw_val, bytes) else raw_val
            try:
                value = json.loads(val_str)
            except Exception:
                value = val_str
                
    elif type_str == "hash":
        raw_val = await redis.hgetall(key)
        value = {}
        for k, v in raw_val.items():
            k_str = k.decode("utf-8") if isinstance(k, bytes) else k
            v_str = v.decode("utf-8") if isinstance(v, bytes) else v
            try:
                value[k_str] = json.loads(v_str)
            except Exception:
                value[k_str] = v_str
                
    elif type_str == "list":
        raw_val = await redis.lrange(key, 0, -1)
        value = []
        for item in raw_val:
            item_str = item.decode("utf-8") if isinstance(item, bytes) else item
            try:
                value.append(json.loads(item_str))
            except Exception:
                value.append(item_str)
                
    elif type_str == "set":
        raw_val = await redis.smembers(key)
        value = []
        for item in raw_val:
            item_str = item.decode("utf-8") if isinstance(item, bytes) else item
            try:
                value.append(json.loads(item_str))
            except Exception:
                value.append(item_str)
                
    elif type_str == "zset":
        raw_val = await redis.zrange(key, 0, -1, withscores=True)
        value = []
        for member, score in raw_val:
            member_str = member.decode("utf-8") if isinstance(member, bytes) else member
            try:
                member_val = json.loads(member_str)
            except Exception:
                member_val = member_str
            value.append({"member": member_val, "score": score})
            
    else:
        # Fallback if other types are present (e.g. streams)
        value = f"<Unsupported type: {type_str}>"
        
    return {
        "status": "OK",
        "key": key,
        "type": type_str,
        "ttl": ttl,
        "value": value
    }
