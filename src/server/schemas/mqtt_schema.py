# src/server/schemas/mqtt_schema.py
from pydantic import BaseModel, Field

class mqtt_subscribe_request(BaseModel):
    topic: str = Field(..., min_length=1, description="The name of the MQTT topic to subscribe to")

class mqtt_subscribe_response(BaseModel):
    status: str
    message: str
