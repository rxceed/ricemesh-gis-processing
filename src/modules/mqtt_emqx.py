"""MQTT client helpers for EMQX broker connections."""

__all__ = ["mqtt_client", "mqtt_publish"]

import os
import aiomqtt
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

_MQTT_HOST = os.getenv("EMQX_MQTT_HOST", "127.0.0.1")
_MQTT_PORT = int(os.getenv("EMQX_MQTT_PORT", 1883))
_MQTT_USER = os.getenv("EMQX_MQTT_USER")
_MQTT_PASS = os.getenv("EMQX_MQTT_PASS")


@asynccontextmanager
async def mqtt_client():
    """Async context manager that yields a connected aiomqtt.Client.

    Reads host, port, username, and password from env vars.
    Raises RuntimeError if credentials are missing.
    """
    if not _MQTT_USER or not _MQTT_PASS:
        raise RuntimeError(
            "EMQX_MQTT_USER and EMQX_MQTT_PASS must be set in environment"
        )

    async with aiomqtt.Client(
        hostname=_MQTT_HOST,
        port=_MQTT_PORT,
        username=_MQTT_USER,
        password=_MQTT_PASS,
    ) as client:
        yield client


async def mqtt_publish(topic: str, payload: str | bytes, qos: int = 1) -> None:
    """Publish a single message and disconnect.
    Args:
        topic:   MQTT topic string.
        payload: Message payload (str or bytes).
        qos:     Quality of service level (0, 1, or 2). Defaults to 1.
    """
    async with mqtt_client() as client:
        await client.publish(topic, payload=payload, qos=qos)
