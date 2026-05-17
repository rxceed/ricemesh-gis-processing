# src/server/services/videoOps_service.py
from pathlib import Path
from fastapi import File, UploadFile
from dotenv import load_dotenv
import os
from bson import ObjectId

from db.models import VideoUpload, ParsedImage
from db.gridfs_ops import gridfs_delete_file

load_dotenv()

BASE_DIR       = Path(__file__).resolve().parents[2]
PARSED_TMP_DIR = BASE_DIR / os.getenv("PARSE_TMP", "tmp/parsed")
TMP_DIR        = BASE_DIR / os.getenv("UPLOAD_TMP", "tmp/uploads").split("/")[0]
UPLOAD_TMP_DIR = BASE_DIR / os.getenv("UPLOAD_TMP")


async def _save_upload_to_disk(file: UploadFile, dest: Path) -> None:
    """
    Stream an UploadFile to disk in 1 MB chunks.
    Seeks to 0 first in case FastAPI partially consumed the stream
    during request validation.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    await file.seek(0)
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)


async def _validate_mp4_magic(file: UploadFile) -> bool:
    """
    Check the file signature (magic numbers) to ensure it's a valid
    ISO base media file (MP4). We check the first 12 bytes for 'ftyp'.
    """
    await file.seek(0)
    header = await file.read(12)
    await file.seek(0)
    
    if len(header) < 12:
        return False
        
    # Standard MP4 files have 'ftyp' at offset 4
    return header[4:8] == b"ftyp"


async def video_upload_service(
    data: dict,
    file: UploadFile = File(...),
    redis=None,
) -> dict:
    """
    Save the uploaded file to disk, enqueue the upload task, and return
    immediately with a job_id.

    Why save to disk before enqueuing?
      UploadFile.file is a SpooledTemporaryFile tied to the HTTP request.
      Once the request handler returns, the file object is gone. The Arq
      worker runs in a separate process and cannot access it. Writing to
      a named temp file gives the worker a stable path to read from.
    """
    # ── Security: Magic Number Check ──────────────────────────────────────
    if not await _validate_mp4_magic(file):
        raise ValueError("Invalid file format: Not a genuine MP4 video.")

    # ── Normalize Extension to lower case .mp4 ────────────────────────────
    filename_path = Path(file.filename)
    if filename_path.suffix.lower() != ".mp4":
        raise ValueError("Invalid file extension: Only .mp4 is supported.")
    
    normalized_filename = filename_path.with_suffix(".mp4").name
    tmp_path = UPLOAD_TMP_DIR / normalized_filename
    await _save_upload_to_disk(file, tmp_path)

    job = await redis.enqueue_job(
        "upload_video",
        owner_id=data.owner_id,
        tmp_path=str(tmp_path),
        filename=normalized_filename,
        content_type="video/mp4",
        file_size=file.size,
    )

    return {
        "job_id":  job.job_id,
        "status":  "queued",
        "message": f"{normalized_filename} queued for upload.",
    }


async def video_parser_service(data: dict, redis=None) -> dict:
    """
    Enqueue a parse job and return immediately with a job_id.
    The worker downloads the video from GridFS, extracts frames, and
    reports progress via Redis.
    """
    job = await redis.enqueue_job(
        "parse_video",
        owner_id=data.owner_id,
        filename=data.filename,
        frame_interval=data.frame_interval,
        start_sec=data.start,
        end_sec=data.end,
    )

    return {
        "job_id":  job.job_id,
        "status":  "queued",
        "message": f"Parsing queued for {data.filename}.",
    }


async def get_video_service(data: dict) -> dict:
    try:
        videos = await VideoUpload.find({"ownerId": data.owner_id}).to_list()
        return {"status": "OK", "videos": videos}
    except Exception as e:
        return e

async def video_webodm_service(data: dict, redis=None) -> dict:
    """
    Enqueue a WebODM processing job and return immediately with a job_id.
    """
    job = await redis.enqueue_job(
        "process_webodm_video",
        owner_id=data.owner_id,
        filename=data.filename,
        project_name=data.project_name,
        task_name=data.task_name,
        options=data.options,
    )

    return {
        "job_id":  job.job_id,
        "status":  "queued",
        "message": f"WebODM processing queued for {data.filename} in project {data.project_name}.",
    }

async def video_delete_service(video_id: str, owner_id: int, db) -> dict:
    video = await VideoUpload.find_one({"_id": ObjectId(video_id), "ownerId": owner_id})
    if not video:
        raise ValueError("Video not found or unauthorized")
    
    await gridfs_delete_file(db, video.gridfs_file_id, bucket_name="videos")
    await video.delete()
    return {"status": "OK", "message": f"Video {video_id} deleted"}

async def parsed_image_delete_service(parsed_id: str, owner_id: int, db) -> dict:
    parsed = await ParsedImage.find_one({"_id": ObjectId(parsed_id), "ownerId": owner_id})
    if not parsed:
        raise ValueError("Parsed image not found or unauthorized")
    
    for frame in parsed.image_frames:
        await gridfs_delete_file(db, frame.gridfs_file_id, bucket_name="parsed_frames")
    
    await parsed.delete()
    return {"status": "OK", "message": f"Parsed image {parsed_id} deleted"}
