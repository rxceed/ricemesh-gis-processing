from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from server.routers.videoOps_route import videoOps_router
from server.routers.webodm_route import webodm_router
import db.connection as conn
from arq import create_pool
from arq.connections import RedisSettings
from server.common import MONGO_URI
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

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
    
    print("Connecting to Redis...")
    redis = await create_pool(
        RedisSettings(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
        ))
    
    yield {"db": db, "client": client, "redis": redis}
    
    print("Closing database connection...")
    try:        
        await conn.close_client(client)
    except Exception as e:
        print(f"Error when closing database connection: {e}")
    print("Database connection closed.")

    print("Closing Redis connection...")
    await redis.close()
    print("Redis connection closed.")

gisProc = FastAPI(title="RiceMesh GIS Processing API", lifespan=lifespan)
origins = [
    "http://localhost",
    "http://localhost:5173",
]

gisProc.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@gisProc.middleware("http")
async def add_state_middleware(request: Request, call_next):
    # lifespan state is accessible via request.app.state
    # but some controllers use request.state directly.
    # We ensure redis is available where expected.
    if hasattr(request.app.state, "redis"):
        request.state.redis = request.app.state.redis
    
    response = await call_next(request)
    return response

gisProc.include_router(videoOps_router)
gisProc.include_router(webodm_router)

@gisProc.get("/", tags=["Health Check"])
async def root():
    return {"message": "server is up and running"}
