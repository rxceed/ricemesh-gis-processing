# src/server/controllers/mqtt_controller.py
from fastapi import HTTPException, status
from server.schemas.mqtt_schema import (
    mqtt_subscribe_request,
    mqtt_subscribe_response,
)
from server.services.mqtt_service import subscribe_topic_service

async def subscribe_topic(ctx: mqtt_subscribe_request) -> mqtt_subscribe_response:
    """
    Controller endpoint to handle subscribing the server to an MQTT topic.
    """
    try:
        res = await subscribe_topic_service(ctx.topic)
        return mqtt_subscribe_response(status=res["status"], message=res["message"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
