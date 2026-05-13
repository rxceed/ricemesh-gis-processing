from modules.parsevid import video_to_frames
from dotenv import load_dotenv
from fastapi import File, UploadFile
from pathlib import Path
from db.gridfs_ops import gridfs_download_file, gridfs_upload_file
from db.models import VideoUpload
import asyncio, os, shutil

load_dotenv()

parsed_tmp_dir_env = os.getenv("PARSE_TMP")
PARSED_TMP_DIR = Path.joinpath(Path.cwd(), parsed_tmp_dir_env)
TMP_DIR = PARSED_TMP_DIR.parent
upload_tmp_dir_env = os.getenv("UPLOAD_TMP")
UPLOAD_TMP_DIR = Path.joinpath(Path.cwd(), upload_tmp_dir_env)

def _video_metadata(file_path: Path):
    try:
        from pymediainfo import MediaInfo
        media_info = MediaInfo.parse(file_path)
        if not media_info or not media_info.tracks:
            raise Exception("Unable to parse media info")
        # Locate the video track (usually the first one)
        video_track = next((t for t in media_info.tracks if t.track_type == 'Video'), None)
        if not video_track:
            raise Exception("No video track found")
        # 1. Extract Framerate
        # Returns a string or float (e.g., "23.976")
        fps = video_track.frame_rate
        # 2. Extract Duration
        # MediaInfo returns duration in milliseconds
        duration_ms = video_track.duration
        duration_sec = float(duration_ms) / 1000 if duration_ms else 0
        # 3. Extract Codec
        # 'format' is the short name (e.g., AVC, HEVC), 
        # 'codec_id' is the specific FourCC (e.g., avc1)
        codec = video_track.format 
        codec_id = video_track.codec_id
        # 4. Extract Resolution
        width = video_track.width
        height = video_track.height
        # Extract metadata
        metadata: dict = {
            "fps": fps,
            "duration": duration_sec,
            "codec": codec,
            "resolution": {"width": width, "height": height}
        }
        if not all(metadata.values()):
            raise Exception("Incomplete metadata extracted")
        return metadata
    except Exception as e:
        return e

async def _write_to_tmp(file: UploadFile, filename: str):
    try:
        CHUNK = 4096 * 1024
        file_path = Path.joinpath(UPLOAD_TMP_DIR, filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        await file.seek(0)
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                buffer.write(chunk)
        return file_path
    except Exception as e:
        return e

async def video_upload_service(data: dict, file: UploadFile=File(...), db=None):
    """
    Args:
        data: dict{owner_id: int}
        file: uploaded file
        db: database connection
    """
    from src.db.connection_beanie import connect_db, connect_client
    try:
        filename = file.filename
        tmp_path = await _write_to_tmp(file, filename)

        metadata = _video_metadata(tmp_path)
        gridfs_id = await gridfs_upload_file(db, tmp_path, filename, bucket_name="videos")

        uploaded_video = VideoUpload(ownerId=data.owner_id,
                                     filename=filename, 
                                     gridfsFileId=gridfs_id,
                                     sizeBytes=file.size, 
                                     mimeType=file.content_type, 
                                     durationSec=metadata['duration'],
                                     fps=metadata['fps'],
                                     resolution=metadata['resolution'],
                                     codec=metadata['codec'])
        
        upload_res = await uploaded_video.insert()

        if not isinstance(upload_res, VideoUpload):
            raise RuntimeError("Beanie insert did not return a VideoUpload document")
            
        return {
            "status": "OK",
            "uploaded_video": upload_res
            }
    except Exception as e:
        return e

async def _download_from_gridfs(db, owner_id: int, filename: str):
    file_path = Path.joinpath(TMP_DIR, f"downloads/{filename}")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if file_path.exists():
        return file_path
    else:
        video_upload = await VideoUpload.find_one({"ownerId": owner_id, "filename": filename})
        if not video_upload:
            raise Exception("File not found")
        await gridfs_download_file(db, video_upload.gridfs_file_id, file_path, bucket_name="videos")
    return file_path

async def video_parser_service(data: dict, db=None):
    """
    Args:
        data: dict{owner_id: int,
                    frame_interval: int=1,
                    start: int=1,
                    end: int | None = None
                    }
    """
    from celery_app.tasks.videoOps_task import parse_video_task
    try:
    # .delay() is Celery shorthand for .apply_async() with positional args.
    # It enqueues the task in RabbitMQ and returns immediately.
        task = parse_video_task.delay(
            owner_id=data.owner_id,
            filename=data.filename,
            frame_interval=data.frame_interval,
            start_sec=data.start,
            end_sec=data.end,
        )
    except Exception as e:
        return e

    return {
        "task_id": task.id,
        "status":  "queued",
        "message": f"Parsing started for {data.filename}. Connect to the stream endpoint for progress.",
    }

async def get_video_service(data: dict):
    """
    Args:
        data: dict{owner_id: int}
    """
    try:
        uploaded_videos = await VideoUpload.find({"ownerId": data.owner_id}).to_list()
        return {
            "status": "OK",
            "videos": uploaded_videos
        }
    except Exception as e:
        return e