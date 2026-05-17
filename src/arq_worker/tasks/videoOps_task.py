# src/arq_worker/tasks/video_tasks.py
"""
Arq task functions for video upload and frame extraction.

Both tasks are async coroutines so they run natively on the worker's
event loop. Heavy I/O (GridFS, MongoDB) is awaited normally.
CPU-bound work (OpenCV frame extraction) is offloaded to the shared
ThreadPoolExecutor via run_in_executor so it never blocks the loop.

Progress is written to Redis under  job_progress:{job_id}  as a JSON
blob.  The FastAPI SSE endpoint polls this key every second and streams
it to the client.
"""
import asyncio
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from datetime import datetime

from bson import ObjectId
from dotenv import load_dotenv
from PIL import Image

from db.gridfs_ops import gridfs_upload_file, gridfs_download_file
from db.models import VideoUpload, ParsedImage, WebODMTask, WebODMAsset
from utils import read_video_metadata
from modules.parsevid import video_to_frames
from server.services.webodm_service import (
    webodm_auth_service,
    webodm_project_get_service,
    webodm_task_create_service,
    webodm_task_get_service,
    webodm_task_download_service,
)


load_dotenv()

# ── Path constants (mirror videoOps_service.py) ───────────────────────────
BASE_DIR       = Path(__file__).resolve().parents[3]
PARSED_TMP_DIR = BASE_DIR / os.getenv("PARSE_TMP", "tmp/parsed")
TMP_DIR        = BASE_DIR / os.getenv("UPLOAD_TMP", "tmp/uploads").split("/")[0]
DOWNLOAD_DIR   = TMP_DIR / "downloads"


# ── Progress helper ───────────────────────────────────────────────────────

async def _set_progress(
    ctx: dict,
    stage: str,
    percent: int,
    message: str,
    **extra,
) -> None:
    """
    Write a progress snapshot to Redis. TTL matches keep_result so the
    key expires at the same time the job result does.
    """
    payload = {"stage": stage, "percent": percent, "message": message, **extra}
    await ctx["redis"].set(
        f"job_progress:{ctx['job_id']}",
        json.dumps(payload),
        ex=86_400,
    )


# ── Task 1: upload video ──────────────────────────────────────────────────

async def upload_video(
    ctx: dict,
    owner_id: int,
    tmp_path: str,       # absolute path on disk — written during the HTTP request
    filename: str,
    content_type: str,
    file_size: int,
) -> dict:
    """
    Upload a video from a local temp file to GridFS, extract metadata,
    persist a VideoUpload document, and delete the temp file.

    The temp file is written synchronously during the HTTP request
    (before the task is enqueued) so this task never needs to buffer
    the entire video in memory.
    """
    path = Path(tmp_path)

    try:
        # ── Stage 1: GridFS upload ────────────────────────────────────────
        await _set_progress(ctx, "uploading", 10, f"Uploading {filename} to GridFS…")

        gridfs_id = await gridfs_upload_file(
            ctx["db"], path, filename, bucket_name="videos"
        )

        # ── Stage 2: metadata extraction ─────────────────────────────────
        # MediaInfo reads the file with a C library — synchronous but fast.
        await _set_progress(ctx, "metadata", 60, "Extracting video metadata…")

        loop     = asyncio.get_event_loop()
        metadata = await loop.run_in_executor(
            ctx["executor"],
            read_video_metadata,
            path,
        )

        # ── Stage 3: persist document ─────────────────────────────────────
        await _set_progress(ctx, "saving", 85, "Saving document…")

        doc = VideoUpload(
            ownerId=owner_id,
            filename=filename,
            gridfsFileId=gridfs_id,
            sizeBytes=file_size,
            mimeType=content_type,
            durationSec=metadata["duration"],
            fps=metadata["fps"],
            resolution=metadata["resolution"],
            codec=metadata["codec"],
        )
        await doc.insert()

        await _set_progress(ctx, "complete", 100, "Upload complete")

        return {
            "status":       "uploaded",
            "filename":     filename,
            "gridfsFileId": str(gridfs_id),
            "durationSec":  metadata["duration"],
            "fps":          metadata["fps"],
        }

    finally:
        # Always clean up the temp file — success or failure.
        # missing_ok=True in case the file was already cleaned up on a retry.
        path.unlink(missing_ok=True)


# ── Batch Processor Helper ────────────────────────────────────────────────

async def _process_frame_batch(
    ctx: dict,
    owner_id: int,
    filename: str,
    batch: list[tuple[Path, int]],
) -> None:
    """
    Concurrent upload of a frame batch to GridFS and atomic document update.
    """
    db = ctx["db"]
    
    # 1. Concurrent upload to GridFS
    upload_tasks = []
    for filepath, frame_index in batch:
        # Use a descriptive filename in GridFS
        gridfs_name = f"{filename}_frame_{frame_index:04d}.png"
        upload_tasks.append(
            gridfs_upload_file(db, filepath, gridfs_name, bucket_name="parsed_frames")
        )
    
    gridfs_ids = await asyncio.gather(*upload_tasks)
    
    # 2. Compile frames list for atomic $push
    new_frames = [
        {"gridfsFileId": gid, "frameIndex": idx}
        for (filepath, idx), gid in zip(batch, gridfs_ids)
    ]
    
    # 3. Atomic $push to ParsedImage document
    await ParsedImage.find_one(
        {"ownerId": owner_id, "filename": filename}
    ).update({"$push": {"imageFrames": {"$each": new_frames}}})


# ── Task 2: parse video ───────────────────────────────────────────────────

async def parse_video(
    ctx: dict,
    owner_id: int,
    filename: str,
    frame_interval: int = 1,
    start_sec: float = 0.0,
    end_sec: float | None = None,
) -> dict:
    """
    Download a video from GridFS, extract frames with OpenCV, and store
    the frame metadata and GridFS file IDs in MongoDB.

    Frames are uploaded to GridFS and pushed to MongoDB in batches of 20
    to ensure high throughput and prevent hitting BSON document limits.
    """
    # ── Stage 1: find video document ─────────────────────────────────────
    await _set_progress(ctx, "fetching", 0, f"Looking up {filename}…")

    video_doc = await VideoUpload.find_one({"ownerId": owner_id, "filename": filename})
    if not video_doc:
        raise FileNotFoundError(
            f"VideoUpload not found: ownerId={owner_id} filename={filename}"
        )

    # ── Stage 2: download from GridFS ─────────────────────────────────────
    dest = DOWNLOAD_DIR / filename

    if not dest.exists():
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        await _set_progress(ctx, "downloading", 5, f"Downloading {filename}…")
        await gridfs_download_file(
            ctx["db"], video_doc.gridfs_file_id, dest, bucket_name="videos"
        )

    # ── Stage 3: frame extraction (CPU-bound) ─────────────────────────────
    # Create/Reset ParsedImage document
    await ParsedImage.find({"ownerId": owner_id, "filename": filename}).delete()
    parsed_image = ParsedImage(ownerId=owner_id, filename=filename, imageFrames=[])
    await parsed_image.insert()

    await _set_progress(ctx, "extracting", 10, "Starting frame extraction…")

    output_dir = PARSED_TMP_DIR / Path(filename).stem
    output_dir.mkdir(parents=True, exist_ok=True)

    loop      = asyncio.get_event_loop()
    throttle  = max(1, 30 // frame_interval)  # report ~once per second of video
    
    frame_batch = []

    def on_progress(saved_count: int, total_frames: int) -> None:
        """
        Called by video_to_frames() inside the worker thread.
        """
        if saved_count % throttle != 0 and saved_count != total_frames:
            return

        percent = 10 + int(saved_count / max(total_frames, 1) * 85)  # 10 → 95 %
        coro = _set_progress(
            ctx, "extracting", percent,
            f"Extracted {saved_count}/{total_frames} frames",
            current_frame=saved_count,
            total_frames=total_frames,
        )
        asyncio.run_coroutine_threadsafe(coro, loop)

    def save_to_db_callback(filepath: Path, frame_index: int) -> None:
        """
        Batch frames and schedule async upload/database update.
        """
        frame_batch.append((filepath, frame_index))
        if len(frame_batch) >= 20:
            batch_to_process = frame_batch[:]
            frame_batch.clear()
            coro = _process_frame_batch(ctx, owner_id, filename, batch_to_process)
            asyncio.run_coroutine_threadsafe(coro, loop)

    extracted_frames, out_path = await loop.run_in_executor(
        ctx["executor"],
        partial(
            video_to_frames,
            dest,
            output_dir,
            start_sec=start_sec,
            end_sec=end_sec,
            frame_interval=frame_interval,
            compression=9,
            on_progress=on_progress,
            save_to_db=save_to_db_callback,
        ),
    )
    
    # Final flush for remaining frames in the last batch
    if frame_batch:
        await _process_frame_batch(ctx, owner_id, filename, frame_batch)

    await _set_progress(
        ctx, "complete", 100,
        f"Extracted {extracted_frames} frames",
        extracted_frames=extracted_frames,
    )

    return {
        "status":           "parsed",
        "filename":         filename,
        "extracted_frames": extracted_frames,
        "output_dir":       str(out_path),
        "frame_interval":   frame_interval,
        "start_sec":        start_sec,
        "end_sec":          end_sec,
    }


# ── Task 3: download parsed frames ─────────────────────────────────────────

async def download_parsed_frames(
    ctx: dict,
    owner_id: int,
    filename: str,
) -> dict:
    """
    Download all frames belonging to a parsed video from GridFS, archive
    them into a ZIP file, and return the path for serving.
    """
    # ── Stage 1: find ParsedImage document ───────────────────────────────
    await _set_progress(ctx, "fetching", 0, f"Looking up parsed frames for {filename}…")

    parsed_image = await ParsedImage.find_one({"ownerId": owner_id, "filename": filename})
    if not parsed_image:
        raise FileNotFoundError(f"No parsed frames found for {filename}")

    # ── Stage 2: prepare destination ──────────────────────────────────────
    stem         = Path(filename).stem
    download_dir = DOWNLOAD_DIR / f"parsed_{stem}_{ctx['job_id']}"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    total_frames = len(parsed_image.image_frames)
    await _set_progress(ctx, "downloading", 10, f"Downloading {total_frames} frames from GridFS…")
    
    # ── Stage 3: concurrent download ──────────────────────────────────────
    dl_tasks = []
    for frame in parsed_image.image_frames:
        frame_path = download_dir / f"frame_{frame.frame_index:04d}.png"
        dl_tasks.append(
            gridfs_download_file(
                ctx["db"], frame.gridfs_file_id, frame_path, bucket_name="parsed_frames"
            )
        )
    
    await asyncio.gather(*dl_tasks)
    
    await _set_progress(ctx, "complete", 100, "Download preparation complete")
    
    return {
        "status":     "ready",
        "output_dir": str(download_dir),
        "filename":   f"parsed_{stem}",
    }


# ── Task 4: WebODM video processing ────────────────────────────────────────

async def process_webodm_video(
    ctx: dict,
    owner_id: int,
    filename: str,
    project_name: str,
    task_name: str | None = None,
    options: list[dict] | None = None,
) -> dict:
    """
    1. Ensure parsed frames are available locally.
    2. Find the WebODM project.
    3. Upload frames and create a WebODM task.
    """
    # ── Stage 1: prepare frames locally ───────────────────────────────────
    stem = Path(filename).stem
    download_dir = DOWNLOAD_DIR / f"parsed_{stem}"
    
    # Check if files already exist in the expected directory
    if not (download_dir.exists() and any(download_dir.iterdir())):
        await _set_progress(ctx, "fetching", 0, f"Downloading frames for {filename}…")
        
        parsed_image = await ParsedImage.find_one({"ownerId": owner_id, "filename": filename})
        if not parsed_image:
            raise FileNotFoundError(f"No parsed frames found for {filename}")
            
        download_dir.mkdir(parents=True, exist_ok=True)
        dl_tasks = []
        for frame in parsed_image.image_frames:
            frame_path = download_dir / f"frame_{frame.frame_index:04d}.png"
            dl_tasks.append(
                gridfs_download_file(
                    ctx["db"], frame.gridfs_file_id, frame_path, bucket_name="parsed_frames"
                )
            )
        await asyncio.gather(*dl_tasks)

    # ── Stage 2: WebODM Authentication & Project Verification ─────────────
    await _set_progress(ctx, "webodm_auth", 40, "Authenticating with WebODM…")
    token = await webodm_auth_service()
    
    await _set_progress(ctx, "webodm_project", 50, f"Finding project '{project_name}'…")
    project_data = await webodm_project_get_service(token, name=project_name)
    
    # WebODM API might return a list or a dict with a 'results' key
    if isinstance(project_data, dict):
        results = project_data.get("results", [])
    elif isinstance(project_data, list):
        results = project_data
    else:
        results = []

    # Find the specific project by name to be safe
    project = next((p for p in results if p.get("name") == project_name), None)
    
    if not project:
        raise ValueError(f"WebODM project '{project_name}' not found. Please create it first.")
    
    project_id = project["id"]

    # ── Stage 3: Task Creation in WebODM ───────────────────────────────────
    await _set_progress(ctx, "webodm_upload", 60, f"Uploading frames to WebODM project {project_id}…")
    
    file_tuples = []
    # Collect all .png files in the download directory
    image_files = sorted(list(download_dir.glob("*.png")))
    
    if not image_files:
         raise FileNotFoundError(f"No image files found in {download_dir}")

    # Read files into memory for the upload service
    # Note: If there are MANY frames, this might use a lot of RAM. 
    # For now, we follow the existing pattern in webodm_controller.
    for img_path in image_files:
        with open(img_path, "rb") as f:
            content = f.read()
            file_tuples.append((img_path.name, content, "image/png"))

    await _set_progress(ctx, "webodm_creating", 90, "Finalizing WebODM task…")
    
    task_data = {}
    if task_name:
        task_data["name"] = task_name
    if options:
        task_data["options"] = options
        
    res = await webodm_task_create_service(project_id, file_tuples, task_data, token)
    
    # Save a WebODMTask tracking document for the periodic status worker
    tracking_task = WebODMTask(
        webodm_task_id=res.get("id"),
        webodm_project_id=project_id,
        owner_id=owner_id,
        project_name=project_name,
        task_name=task_name or res.get("name", "Unnamed Task"),
    )
    await tracking_task.insert()
    
    await _set_progress(ctx, "complete", 100, f"WebODM task created: {res.get('id')}")
    
    return {
        "status": "ready",
        "webodm_task_id": res.get("id"),
        "project_id": project_id,
        "project_name": project_name
    }


# ── Task 5: Periodic WebODM status check ───────────────────────────────────

async def check_webodm_tasks(ctx: dict) -> None:
    """
    Cron task that runs every minute to check the status of pending
    WebODM tasks. Downloads and uploads assets (orthophoto) upon completion.
    """
    # Beanie initialization check (ctx["db"] is set in arq_worker/settings.py)
    # Beanie models should already be initialized if arq is running.
    
    pending_tasks = await WebODMTask.find({"is_processed": False}).to_list()
    if not pending_tasks:
        return

    print(f"[arq] checking {len(pending_tasks)} pending WebODM tasks…")
    
    try:
        token = await webodm_auth_service()
    except Exception as e:
        print(f"[arq] failed to authenticate with WebODM: {e}")
        return

    for task in pending_tasks:
        try:
            # 1. Get current status from WebODM
            # WebODM status codes: 10 (Queued), 20 (Running), 30 (Failed), 40 (Completed)
            status_data = await webodm_task_get_service(task.webodm_project_id, token, task_id=task.webodm_task_id)
            
            # WebODM returns a nested status object
            status_obj = status_data.get("status", {})
            status_code = status_obj.get("code")
            
            if status_code == 40: # COMPLETED
                print(f"[arq] WebODM task {task.webodm_task_id} completed. Downloading orthophoto…")
                
                # 2. Download orthophoto.tif
                res = await webodm_task_download_service(task.project_name, task.task_name, "orthophoto.tif", token)
                
                # 3. Save to temp file
                tmp_tif = DOWNLOAD_DIR / f"{task.webodm_task_id}_orthophoto.tif"
                tmp_tif.parent.mkdir(parents=True, exist_ok=True)
                
                with open(tmp_tif, "wb") as f:
                    for chunk in res.iter_content(chunk_size=1024*1024):
                        f.write(chunk)
                
                # 4. Extract metadata (size & resolution)
                file_size = tmp_tif.stat().st_size
                
                # Use PIL to get resolution. TIFF files can be large, but PIL.Image.open is lazy.
                with Image.open(tmp_tif) as img:
                    width, height = img.size
                
                # 5. Upload to GridFS
                gridfs_id = await gridfs_upload_file(ctx["db"], tmp_tif, f"{task.task_name}_orthophoto.tif", bucket_name="webodm_assets")
                
                # 6. Create WebODMAsset record
                asset = WebODMAsset(
                    gridfs_file_id=gridfs_id,
                    owner_id=task.owner_id,
                    project_name=task.project_name,
                    project_id=task.webodm_project_id,
                    task_name=task.task_name,
                    task_id=task.webodm_task_id,
                    file_size_bytes=file_size,
                    resolution=[width, height]
                )
                await asset.insert()
                
                # 7. Update tracking task
                task.is_processed = True
                task.status = "completed"
                await task.save()
                
                # Clean up
                tmp_tif.unlink(missing_ok=True)
                print(f"[arq] Successfully processed asset for task {task.webodm_task_id}")
                
            elif status_code == 30: # FAILED
                print(f"[arq] WebODM task {task.webodm_task_id} failed.")
                task.is_processed = True
                task.status = "failed"
                await task.save()
                
            else:
                # Still running or queued, update status in DB
                status_name = status_obj.get("name", "unknown")
                if task.status != status_name:
                    task.status = status_name
                    await task.save()

        except Exception as e:
            print(f"[arq] error checking task {task.webodm_task_id}: {e}")
