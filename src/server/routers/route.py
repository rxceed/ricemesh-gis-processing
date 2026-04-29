from fastapi import APIRouter, Depends, File, UploadFile
from server.schemas.videoParser_schema import parserBase
from server.controllers.videoParser_controller import video_parser

router = APIRouter(prefix="/api")

@router.post("/parse", status_code=201)
async def parse(parse: parserBase = Depends(), file: UploadFile=File(...)):
    return await video_parser(ctx=parse, file=file)