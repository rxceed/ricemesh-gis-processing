__all__ = ["init_db"]

from pymongo import AsyncMongoClient

async def connect_client(mongo_uri: str):
    from pymongo import AsyncMongoClient
    return AsyncMongoClient(mongo_uri)

async def connect_db(mongo_client: AsyncMongoClient):
    from dotenv import load_dotenv
    import os
    load_dotenv()
    DB_NAME = os.getenv("DATABASE")
    try:
        return mongo_client[DB_NAME]
    except Exception as e:
        return e
    
async def close_client(mongo_client: AsyncMongoClient):
    try:
        await mongo_client.close()
    except Exception as e:
        return e
    
async def init_db(db):
    """
    Call once at FastAPI startup.
    motor.motor_asyncio.AsyncIOMotorClient is the async driver Beanie wraps.
    """
    from beanie import init_beanie
    from db.models import VideoUpload, ParsedImage
    try:
        await init_beanie(
            database=db,
            document_models=[
                VideoUpload,
                    ParsedImage
                ],
            )
    except Exception as e:
        return e