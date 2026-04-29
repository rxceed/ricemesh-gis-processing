from fastapi import FastAPI
from server.routers.route import router

gisProc = FastAPI(title="RiceMesh GIS Processing API")

gisProc.include_router(router)

@gisProc.get("/", tags=["Health Check"])
async def root():
    return {"message": "server is up and running"}