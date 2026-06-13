# src/server/routers/mqtt_route.py
from fastapi import APIRouter

from server.schemas.mqtt_schema import (
    mqtt_subscribe_request as _mqtt_subscribe_request,
    mqtt_subscribe_response as _mqtt_subscribe_response,
)
from server.controllers.mqtt_controller import subscribe_topic as _subscribe_topic

mqtt_router = APIRouter(prefix="/api/mqtt", tags=["MQTT"])


@mqtt_router.post("/subscribe", status_code=200, response_model=_mqtt_subscribe_response)
async def subscribe_mqtt_topic(ctx: _mqtt_subscribe_request):
    """
    POST request endpoint that makes the server subscribe to an MQTT topic dynamically.
    """
    return await _subscribe_topic(ctx)
