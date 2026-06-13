"""Persistent MQTT listener that subscribes to device topics on startup."""

__all__ = ["start_mqtt_listener", "subscribe_to_topic"]

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

_subscribed_topics: set[str] = set()
_mqtt_client: aiomqtt.Client | None = None


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
            async with aiomqtt.Client(
                hostname=_MQTT_HOST,
                port=_MQTT_PORT,
                username=_MQTT_USER,
                password=_MQTT_PASS,
            ) as client:
                _mqtt_client = client

                # Subscribe to all currently registered topics
                current_topics = list(_subscribed_topics)
                for topic in current_topics:
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
