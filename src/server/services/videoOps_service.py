# src/server/services/videoOps_service.py
from pathlib import Path
from fastapi import File, UploadFile
from dotenv import load_dotenv
import os
from bson import ObjectId
from typing import Optional

from db.models import VideoUpload, ParsedImage, frames
from db.gridfs_ops import gridfs_delete_file, gridfs_upload_file

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
    srt_file: Optional[UploadFile] = None,
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

    srt_content = None
    if srt_file:
        srt_bytes = await srt_file.read()
        srt_content = srt_bytes.decode("utf-8", errors="ignore")

    job = await redis.enqueue_job(
        "upload_video",
        owner_id=data.owner_id,
        tmp_path=str(tmp_path),
        filename=normalized_filename,
        content_type="video/mp4",
        file_size=file.size,
        srt_content=srt_content,
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
    if getattr(data, "srt_content", None) is not None:
        video_doc = await VideoUpload.find_one({"ownerId": data.owner_id, "filename": data.filename})
        if video_doc:
            video_doc.srt_content = data.srt_content
            await video_doc.save()

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


async def update_video_srt_service(video_id: str, owner_id: str, srt_content: str) -> dict:
    video = await VideoUpload.find_one({"_id": ObjectId(video_id), "ownerId": owner_id})
    if not video:
        raise ValueError("Video not found or unauthorized")
    
    video.srt_content = srt_content
    await video.save()
    return {"status": "OK", "message": "SRT file updated successfully"}


async def get_video_service(data: dict) -> dict:
    try:
        videos = await VideoUpload.find({"ownerId": data.owner_id}).to_list()
        return {"status": "OK", "video": videos}
    except Exception as e:
        raise e

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

async def video_delete_service(video_id: str, owner_id: str, db) -> dict:
    video = await VideoUpload.find_one({"_id": ObjectId(video_id), "ownerId": owner_id})
    if not video:
        raise ValueError("Video not found or unauthorized")
    
    await gridfs_delete_file(db, video.gridfs_file_id, bucket_name="videos")
    await video.delete()
    return {"status": "OK", "message": f"Video {video_id} deleted"}

async def parsed_image_delete_service(parsed_id: str, owner_id: str, db) -> dict:
    parsed = await ParsedImage.find_one({"_id": ObjectId(parsed_id), "ownerId": owner_id})
    if not parsed:
        raise ValueError("Parsed image not found or unauthorized")
    
    for frame in parsed.image_frames:
        await gridfs_delete_file(db, frame.gridfs_file_id, bucket_name="parsed_frames")
    
    await parsed.delete()
    return {"status": "OK", "message": f"Parsed image {parsed_id} deleted"}


async def get_parsed_images_service(
    owner_id: str | None = None,
    filename: str | None = None,
) -> dict:
    """Return parsed image documents, optionally filtered by owner_id and/or filename."""
    query_filters = []

    if owner_id:
        query_filters.append(ParsedImage.owner_id == owner_id)
    if filename:
        query_filters.append(ParsedImage.filename == filename)

    if query_filters:
        images = await ParsedImage.find(*query_filters).to_list()
    else:
        images = await ParsedImage.find_all().to_list()

    return {"status": "OK", "images": images}


async def upload_parsed_images_service(
    owner_id: str,
    filename: str,
    files: list[UploadFile],
    db,
) -> dict:
    """
    Directly upload multiple parsed image files to GridFS and store/overwrite
    the ParsedImage document in MongoDB.
    """
    # ── Clean up existing ParsedImage document and its GridFS files ───────
    existing = await ParsedImage.find_one({"ownerId": owner_id, "filename": filename})
    if existing:
        for frame in existing.image_frames:
            try:
                await gridfs_delete_file(db, frame.gridfs_file_id, bucket_name="parsed_frames")
            except Exception as e:
                # Log and continue deletion of other frames
                print(f"Error deleting GridFS file {frame.gridfs_file_id} during cleanup: {e}")
        await existing.delete()

    # ── Upload new frames ─────────────────────────────────────────────────
    uploaded_gridfs_ids = []
    temp_files_to_clean = []
    try:
        PARSED_TMP_DIR.mkdir(parents=True, exist_ok=True)
        image_frames = []
        
        for idx, file in enumerate(files, start=1):
            ext = Path(file.filename).suffix
            # Use unique name for disk write to avoid collisions
            import uuid
            temp_filename = f"{uuid.uuid4()}_{idx:04d}{ext}"
            temp_path = PARSED_TMP_DIR / temp_filename
            temp_files_to_clean.append(temp_path)
            
            await _save_upload_to_disk(file, temp_path)
            
            # Upload to GridFS
            gridfs_name = f"{filename}_frame_{idx:04d}{ext}"
            gridfs_id = await gridfs_upload_file(db, temp_path, gridfs_name, bucket_name="parsed_frames")
            uploaded_gridfs_ids.append(gridfs_id)
            
            # Remove disk temp file immediately
            if temp_path.exists():
                temp_path.unlink()
                temp_files_to_clean.remove(temp_path)
                
            image_frames.append(frames(gridfsFileId=gridfs_id, frameIndex=idx))
            
    except Exception as e:
        # Cleanup GridFS uploads on failure
        for gridfs_id in uploaded_gridfs_ids:
            try:
                await gridfs_delete_file(db, gridfs_id, bucket_name="parsed_frames")
            except Exception:
                pass
        # Cleanup any leftover disk temp files
        for temp_path in temp_files_to_clean:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
        raise e

    # ── Create and insert ParsedImage document ────────────────────────────
    parsed_image = ParsedImage(
        ownerId=owner_id,
        filename=filename,
        imageFrames=image_frames,
    )
    await parsed_image.insert()

    return {
        "status": "OK",
        "message": f"Successfully uploaded {len(files)} parsed images for {filename}",
        "image": parsed_image,
    }

