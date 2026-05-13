__all__ = ["init_db"]

from pymongo import MongoClient

async def connect_client(mongo_uri: str):
    from pymongo import MongoClient
    return MongoClient(mongo_uri)

async def connect_db(mongo_client: MongoClient):
    from dotenv import load_dotenv
    import os
    load_dotenv()
    DB_NAME = os.getenv("DATABASE")
    try:
        return mongo_client[DB_NAME]
    except Exception as e:
        return e
    
async def close_client(mongo_client: MongoClient):
    try:
        await mongo_client.close()
    except Exception as e:
        return e
    
async def init_db(db):
    """
    Call once at FastAPI startup.
    motor.motor_asyncio.AsyncIOMotorClient is the async driver Beanie wraps.
    """
    from bunnet import init_bunnet
    from db.models.bunnet import VideoUpload, ParsedImage, frames
    try:
        await init_bunnet(
            database=db,
            document_models=[
                    VideoUpload,
                    ParsedImage,
                    frames
                ],
            )
    except Exception as e:
        return e