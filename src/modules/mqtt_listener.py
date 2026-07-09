"""Persistent MQTT listener that subscribes to device topics on startup."""

__all__ = ["start_mqtt_listener", "subscribe_to_topic"]

import asyncio
import json
import os
import aiomqtt
import struct as _struct
import httpx as _httpx
from dotenv import load_dotenv

load_dotenv(override=True)

_MQTT_HOST = os.getenv("EMQX_MQTT_HOST", "127.0.0.1")
_MQTT_PORT = int(os.getenv("EMQX_MQTT_PORT", 1883))
_MQTT_USER = os.getenv("EMQX_MQTT_USER")
_MQTT_PASS = os.getenv("EMQX_MQTT_PASS")

# Redis key prefix for cached MQTT messages
_CACHE_KEY_PREFIX = "mqtt_message"

_subscribed_topics: set[str] = set()
_mqtt_client: aiomqtt.Client | None = None
_api_token: str | None = None


def _uint32_to_float(value: int) -> float:
    """
    Konversi uint32 ke IEEE 754 single-precision float.
    
    Args:
        value: integer unsigned 32-bit (0 sampai 4294967295)
    
    Returns:
        float IEEE 754
    
    Raises:
        ValueError: jika value di luar range uint32
    """
    if not isinstance(value, int):
        raise TypeError(f"Value harus bertipe int, dapat: {type(value)}")
    if not (0 <= value <= 0xFFFFFFFF):
        raise ValueError(f"Value harus dalam range [0, 4294967295], dapat: {value}")
    
    packed = _struct.pack('>I', value)
    result = _struct.unpack('>f', packed)[0]
    return result


def _uint32_to_float_manual(value: int) -> dict:
    """
    Versi manual — ekstrak sign, exponent, mantissa secara eksplisit.
    Berguna untuk debugging / edukasi.
    
    Returns dict dengan breakdown komponen IEEE 754.
    """
    if not isinstance(value, int):
        raise TypeError(f"Value harus bertipe int, dapat: {type(value)}")
    if not (0 <= value <= 0xFFFFFFFF):
        raise ValueError(f"Value harus dalam range [0, 4294967295], dapat: {value}")
    
    sign_bit     = (value >> 31) & 0x1
    exponent_raw = (value >> 23) & 0xFF
    mantissa     = value & 0x7FFFFF

    if exponent_raw == 0xFF:
        if mantissa == 0:
            result = float('-inf') if sign_bit else float('inf')
            category = "infinity"
        else:
            result = float('nan')
            category = "nan"
    elif exponent_raw == 0:
        exponent_actual = -126
        fraction = mantissa / (2**23)
        result = ((-1)**sign_bit) * fraction * (2**exponent_actual)
        category = "subnormal"
    else:
        exponent_actual = exponent_raw - 127
        fraction = 1 + mantissa / (2**23)
        result = ((-1)**sign_bit) * fraction * (2**exponent_actual)
        category = "normalized"

    return {
        "float_value": result,
        "sign_bit": sign_bit,
        "exponent_raw": exponent_raw,
        "exponent_actual": exponent_actual if exponent_raw not in (0, 0xFF) else None,
        "mantissa_bits": mantissa,
        "category": category,
        "hex": f"0x{value:08X}",
        "binary": f"{value:032b}",
    }


async def _login_and_get_token(client: _httpx.AsyncClient, host: str) -> str:
    """Authenticate with the RiceMesh API and return the Bearer JWT token."""
    global _api_token
    email = os.getenv("RICEMESH_API_EMAIL")
    password = os.getenv("RICEMESH_API_PASS")
    if not email or not password:
        raise ValueError("RICEMESH_API_EMAIL and RICEMESH_API_PASS must be set in environment")

    # Try auth/login first, then fall back to /login
    login_url = f"{host}/auth/login"
    try:
        resp = await client.post(login_url, json={"email": email, "password": password})
        if resp.status_code == 404:
            login_url = f"{host}/login"
            resp = await client.post(login_url, json={"email": email, "password": password})
    except Exception:
        login_url = f"{host}/login"
        resp = await client.post(login_url, json={"email": email, "password": password})

    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: HTTP {resp.status_code} — {resp.text}")

    body = resp.json()
    data = body.get("data")
    if isinstance(data, dict):
        token = data.get("access_token")
    else:
        token = body.get("access_token") or body.get("token")

    if not token:
        raise RuntimeError(f"Login response did not contain token: {body}")

    _api_token = token
    return token


async def _on_message(message: aiomqtt.Message, redis) -> None:
    """Handle an incoming MQTT message and cache it in Redis.

    Stores the payload under key `mqtt_message:<topic>`.
    Attempts JSON decode for structured payloads; falls back to raw string.

    Args:
        message: Incoming aiomqtt message with .topic and .payload.
        redis:   Arq Redis pool used for caching.
    """
    topic   = str(message.topic)
    raw     = message.payload.decode(errors="replace")

    # Attempt JSON decode; store as-is string if not valid JSON
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw

    cache_value = json.dumps({
        "topic":   topic,
        "payload": payload,
    })

    cache_key = f"{_CACHE_KEY_PREFIX}:{topic}"
    await redis.set(cache_key, cache_value)

    print(f"[mqtt] Cached {cache_key}")

    # Process structured device telemetry data and send to backend API
    if isinstance(payload, dict) and "device" in payload:
        device_data = payload["device"]
        if isinstance(device_data, list):
            parsed_devices = []
            for item in device_data:
                if isinstance(item, dict):
                    distance = item.get("d")
                    parsed_devices.append({
                        "distance": 100 - distance if distance is not None else None,
                        "temperature": item.get("temperature"),
                        "pressure": item.get("pressure")
                    })
            # Send POST request to host/telemetry/records
            host = os.getenv("RICEMESH_API_HOST")
            if host:
                post_url = f"{host}/telemetry/records"
                
                # Extract device_code from the topic: device/{device_code}/{serial_number}
                device_code = None
                topic_parts = topic.split("/")
                if len(topic_parts) >= 2 and topic_parts[0] == "device":
                    device_code = topic_parts[1]
                
                post_body = {
                    "device": parsed_devices,
                    "device_code": device_code
                }
                print(post_body)
                try:
                    global _api_token
                    async with _httpx.AsyncClient(timeout=10) as client:
                        if not _api_token:
                            await _login_and_get_token(client, host)
                        
                        headers = {"Authorization": f"Bearer {_api_token}"}
                        resp = await client.post(post_url, json=post_body, headers=headers)
                        
                        if resp.status_code in (401, 403):
                            print("[mqtt] Token expired or unauthorized. Re-authenticating...")
                            token = await _login_and_get_token(client, host)
                            headers = {"Authorization": f"Bearer {token}"}
                            resp = await client.post(post_url, json=post_body, headers=headers)

                        print(f"[mqtt] Sent telemetry to {post_url}, status={resp.status_code}")
                except Exception as post_err:
                    print(f"[mqtt] Error sending telemetry to {post_url}: {post_err}")


async def _listen_loop(redis) -> None:
    """Connect to the broker, subscribe to all topics, and process messages indefinitely.

    Reconnects with exponential back-off (max 60 s) on connection loss.

    Args:
        redis:  Arq Redis pool for caching incoming messages.
    """
    global _mqtt_client

    if not _MQTT_USER or not _MQTT_PASS:
        raise RuntimeError(
            "EMQX_MQTT_USER and EMQX_MQTT_PASS must be set in environment"
        )

    backoff = 1

    while True:
        try:
            print(f"[mqtt] Connecting to broker at {_MQTT_HOST}:{_MQTT_PORT}…")
            async with aiomqtt.Client(
                hostname=_MQTT_HOST,
                port=_MQTT_PORT,
                username=_MQTT_USER,
                password=_MQTT_PASS,
            ) as client:
                _mqtt_client = client
                print(f"[mqtt] Connected to broker at {_MQTT_HOST}:{_MQTT_PORT}")

                # Subscribe to all currently registered topics
                current_topics = list(_subscribed_topics)
                for topic in current_topics:
                    await client.subscribe(topic, qos=1)
                    print(f"[mqtt] Subscribed to: {topic}")

                backoff = 1  # reset on successful connection

                async for message in client.messages:
                    await _on_message(message, redis)

        except (aiomqtt.MqttError, Exception) as e:
            print(f"[mqtt] Connection lost or failed ({e}). Reconnecting in {backoff}s…")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

        except asyncio.CancelledError:
            print("[mqtt] Listener cancelled — shutting down.")
            return
        finally:
            _mqtt_client = None


def start_mqtt_listener(topics: list[str], redis) -> asyncio.Task:
    """Spawn the MQTT listen loop as a background asyncio Task.

    Args:
        topics: MQTT topic strings scraped from the devices API.
        redis:  Arq Redis pool passed through to the message handler for caching.

    Returns:
        The running asyncio.Task so the caller can cancel it on shutdown.
    """
    global _subscribed_topics
    _subscribed_topics.update(topics)
    return asyncio.create_task(
        _listen_loop(redis),
        name="mqtt_listener",
    )


async def subscribe_to_topic(topic: str) -> bool:
    """Subscribe to a new MQTT topic and add it to the active listener.

    If the listener is currently connected, it subscribes immediately.
    The topic is added to the subscription list so it persists across reconnects.

    Args:
        topic: The name of the MQTT topic to subscribe to.

    Returns:
        True if subscribed immediately, False if queued (client not connected yet).
    """
    if not topic:
        raise ValueError("Topic name cannot be empty")

    if topic in _subscribed_topics:
        return _mqtt_client is not None

    _subscribed_topics.add(topic)
    if _mqtt_client is not None:
        await _mqtt_client.subscribe(topic, qos=1)
        print(f"[mqtt] Dynamically subscribed to: {topic}")
        return True
    return False
