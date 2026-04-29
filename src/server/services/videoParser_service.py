from modules.parsevid import video_to_frames
from dotenv import load_dotenv
from server.schemas.videoParser_schema import parserBase
from fastapi import File, UploadFile, Depends
from pathlib import Path
import shutil
import os

load_dotenv()

upload_tmp_dir_env = os.getenv("UPLOAD_TMP")
parsed_tmp_dir_env = os.getenv("PARSE_TMP")
UPLOAD_TMP_DIR = Path.joinpath(Path.cwd(), upload_tmp_dir_env)
PARSED_TMP_DIR = Path.joinpath(Path.cwd(), parsed_tmp_dir_env)

async def video_parser_service(ctx: parserBase = Depends(), file: UploadFile=File(...)):
    try:
        filename = Path(file.filename)
        file_path = Path.joinpath(UPLOAD_TMP_DIR, filename)
        parsed_path = Path.joinpath(PARSED_TMP_DIR, filename.stem)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        extracted_frame, outpath = video_to_frames(video_path=file_path,
                                                    output_dir=parsed_path,
                                                    start_sec=ctx.start,
                                                    end_sec=ctx.end,
                                                    frame_interval=ctx.frame_interval,
                                                    compression=9)
        return {
            "status": "OK",
            "file_name": filename,
            "frame_interval": ctx.frame_interval,
            "start_sec": ctx.start,
            "end_sec": ctx.end,
            "extracted_frames": extracted_frame}
    except Exception as e:
        return e