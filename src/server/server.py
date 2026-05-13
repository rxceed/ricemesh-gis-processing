from fastapi import FastAPI
from contextlib import asynccontextmanager
from server.routers.videoOps_route import videoOps_router
import db.connection_beanie as conn
from server.common import MONGO_URI

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Connecting to database...")
    try:
        client = await conn.connect_client(MONGO_URI)
        db = await conn.connect_db(client)
        await conn.init_db(db)
    except Exception as e:
        print(f"Error when connecting to database: {e}")
    print("Connection successful!")
    yield {"db": db, "client": client}
    print("Closing database connection...")
    try:        
        await conn.close_client(client)
    except Exception as e:
        print(f"Error when closing database connection: {e}")
    print("Database connection closed.")

gisProc = FastAPI(title="RiceMesh GIS Processing API", lifespan=lifespan)

gisProc.include_router(videoOps_router)

@gisProc.get("/", tags=["Health Check"])
async def root():
    return {"message": "server is up and running"}