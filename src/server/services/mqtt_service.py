# src/server/services/mqtt_service.py
from modules.mqtt_listener import subscribe_to_topic

async def subscribe_topic_service(topic: str) -> dict:
    """
    Subscribes the server to the given MQTT topic dynamically.
    
    Parameters
    ----------
    topic : str
        The name of the MQTT topic to subscribe to.
        
    Returns
    -------
    dict
        Status dict indicating if subscription succeeded immediately or was queued.
    """
    try:
        subscribed = await subscribe_to_topic(topic)
        if subscribed:
            return {
                "status": "OK",
                "message": f"Successfully subscribed to topic: {topic}"
            }
        else:
            return {
                "status": "QUEUED",
                "message": f"Topic '{topic}' added to subscription list; will subscribe once connected."
            }
    except ValueError as e:
        raise ValueError(str(e))
    except Exception as e:
        raise RuntimeError(f"Failed to subscribe to topic '{topic}': {str(e)}")
