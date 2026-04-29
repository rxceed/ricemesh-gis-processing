from server.services.videoParser_service import video_parser_service
from server.schemas.videoParser_schema import parserBase
from fastapi import File, UploadFile, Depends, HTTPException, status

async def video_parser(ctx: parserBase = Depends(), file: UploadFile = File(...)):
    try:
        filename = file.filename
        file_format = filename.split(".")[1]
        if not(file_format == "mp4" or file_format == "MP4"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video format and extension must be in .mp4 or .MP4")
        res = await video_parser_service(ctx, file)
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")