from server.schemas.videoOps_schema import videoOpsParse, videoOpsBase
from server.services.videoOps_service import get_video_service, video_parser_service, video_upload_service

from fastapi import File, UploadFile, HTTPException, status, Request

async def video_upload(req: Request, ctx: videoOpsBase, file: UploadFile = File(...)):
    try:
        filename = file.filename
        file_format = filename.split(".")[1]
        if not(file_format == "mp4" or file_format == "MP4"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video format and extension must be in .mp4 or .MP4")
        res = await video_upload_service(ctx, file, db=req.state.db)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured during video upload: {res}")
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")

async def video_parser(req: Request, ctx: videoOpsParse):
    try:
        res = await video_parser_service(ctx, db=req.state.db)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {res}")
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")
    
async def get_video(req: Request, ctx: videoOpsBase):
    try:
        res = await get_video_service(ctx)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {res}")
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")