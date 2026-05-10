from fastapi import APIRouter, Depends, File, UploadFile, responses, Request
from typing import Annotated
from server.schemas.videoOps_schema import videoOpsBase, videoOpsParse
from server.controllers.videoOps_controller import video_parser as _video_parser, video_upload as _video_upload, get_video as _get_video

videoOps_router = APIRouter(prefix="/api/video-ops")

@videoOps_router.post("/upload", status_code=201, response_class=responses.JSONResponse)
async def upload(req: Request, upload: Annotated[videoOpsBase, Depends()], file: UploadFile=File(...)):
    return await _video_upload(req=req, ctx=upload, file=file)

@videoOps_router.post("/parse", status_code=201, response_class=responses.JSONResponse)
async def parse(req: Request, parse: Annotated[videoOpsParse, Depends()]):
    return await _video_parser(req=req, ctx=parse)

@videoOps_router.post("/get", status_code=200, response_class=responses.JSONResponse)
async def get(req: Request, get: Annotated[videoOpsBase, Depends()]):
    return await _get_video(req=req, ctx=get)