"""Persistent MQTT listener that subscribes to device topics on startup."""

__all__ = ["start_mqtt_listener"]

import asyncio
import json
import os
import aiomqtt
from dotenv import load_dotenv

load_dotenv()

_MQTT_HOST = os.getenv("EMQX_MQTT_HOST", "127.0.0.1")
_MQTT_PORT = int(os.getenv("EMQX_MQTT_PORT", 1883))
_MQTT_USER = os.getenv("EMQX_MQTT_USER")
_MQTT_PASS = os.getenv("EMQX_MQTT_PASS")

# Redis key prefix for cached MQTT messages
_CACHE_KEY_PREFIX = "mqtt_message"


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


async def _listen_loop(topics: list[str], redis) -> None:
    """Connect to the broker, subscribe to all topics, and process messages indefinitely.

    Reconnects with exponential back-off (max 60 s) on connection loss.

    Args:
        topics: List of MQTT topic strings to subscribe to.
        redis:  Arq Redis pool for caching incoming messages.
    """
    if not topics:
        print("[mqtt] No topics to subscribe to — listener not started.")
        return

    if not _MQTT_USER or not _MQTT_PASS:
        raise RuntimeError(
            "EMQX_MQTT_USER and EMQX_MQTT_PASS must be set in environment"
        )

    backoff = 1

    while True:
        try:
            async with aiomqtt.Client(
                hostname=_MQTT_HOST,
                port=_MQTT_PORT,
                username=_MQTT_USER,
                password=_MQTT_PASS,
            ) as client:
                # Subscribe to every device topic
                for topic in topics:
                    await client.subscribe(topic, qos=1)
                    print(f"[mqtt] Subscribed to: {topic}")

                backoff = 1  # reset on successful connection

                async for message in client.messages:
                    await _on_message(message, redis)

        except aiomqtt.MqttError as e:
            print(f"[mqtt] Connection lost ({e}). Reconnecting in {backoff}s…")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

        except asyncio.CancelledError:
            print("[mqtt] Listener cancelled — shutting down.")
            return


def start_mqtt_listener(topics: list[str], redis) -> asyncio.Task:
    """Spawn the MQTT listen loop as a background asyncio Task.

    Args:
        topics: MQTT topic strings scraped from the devices API.
        redis:  Arq Redis pool passed through to the message handler for caching.

    Returns:
        The running asyncio.Task so the caller can cancel it on shutdown.
    """
    return asyncio.create_task(
        _listen_loop(topics, redis),
        name="mqtt_listener",
    )
