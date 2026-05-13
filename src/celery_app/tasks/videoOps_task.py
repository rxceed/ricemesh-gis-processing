"""
src/celery_app/tasks/video_tasks.py

The Celery task that runs video frame extraction in a worker process.

Why synchronous PyMongo instead of Motor/Beanie here?
  Celery workers are synchronous processes. Motor requires a running
  asyncio event loop. While asyncio.run() can create one, mixing sync
  and async this way is fragile. Synchronous PyMongo is simpler,
  well-tested in worker contexts, and perfectly adequate for the
  sequential I/O operations this task performs.

Task states emitted:
  STARTED   → worker picked up the task (automatic, via track_started)
  PROGRESS  → frame extraction underway (manual, via update_state)
  SUCCESS   → task completed normally
  FAILURE   → unhandled exception (automatic)
"""
import os
import gridfs
import pymongo
from pathlib import Path
from celery import Task
from celery.utils.log import get_task_logger
from dotenv import load_dotenv

from celery_app.app import celery_app
from modules.parsevid import video_to_frames

from db.models.bunnet.bunnet_model import VideoUpload, ParsedImage, frames
from beanie.operators import Push

from server.common import MONGO_URI

load_dotenv()

logger = get_task_logger(__name__)

# ── Paths (mirror videoOps_service.py) ───────────────────────────────────
PARSED_TMP_DIR = Path.cwd() / os.getenv("PARSE_TMP", "tmp/parsed")
TMP_DIR        = Path.cwd() / os.getenv("UPLOAD_TMP", "tmp/uploads").split("/")[0]
DOWNLOAD_DIR   = TMP_DIR / "downloads"


# ── Sync DB helpers (worker-local, no Motor) ──────────────────────────────

def _get_sync_db():
    """
    Open a PyMongo connection local to this worker process.
    Do not cache at module level — Celery forks workers, and
    a cached connection from before the fork will be in an
    inconsistent state in the child process.
    """
    client = pymongo.MongoClient(MONGO_URI)
    return client[os.getenv("DATABASE")]


def _download_video_sync(db, owner_id: int, filename: str) -> Path:
    """
    Download a video from GridFS to disk. Returns the local Path.
    Skips the download if the file already exists (idempotent).
    """
    dest = DOWNLOAD_DIR / filename
    if dest.exists():
        logger.info("Video already on disk, skipping download: %s", filename)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    video_doc = VideoUpload.find_one({"ownerId": owner_id, "filename": filename})

    if not video_doc:
        raise FileNotFoundError(f"VideoUpload document not found: filename={filename}")

    file_id = video_doc.gridfsFileId
    fs      = gridfs.GridFS(db, collection="videos")

    logger.info("Downloading %s from GridFS (id=%s)...", filename, file_id)
    grid_out = fs.get(file_id)

    with open(dest, "wb") as f:
        # Read in 4MB chunks — keeps memory flat for large videos
        while True:
            chunk = grid_out.read(4 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    logger.info("Download complete: %s (%d bytes)", dest, dest.stat().st_size)
    return dest


# ── The task ──────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,                 # gives self access for update_state
    name="ricemesh.tasks.video.parse",
    max_retries=3,
    default_retry_delay=10,    # seconds between retries on transient failure
)
def parse_video_task(
    self: Task,
    owner_id: int,
    filename: str,
    frame_interval: int = 1,
    start_sec: float = 0.0,
    end_sec: float | None = None,
) -> dict:  
    """
    Download a video from GridFS and extract frames to disk.

    Progress is reported via Celery's update_state() so the FastAPI
    SSE endpoint can stream live percentages to the client.

    Returns a dict stored as the task result in MongoDB:
        {
            "filename":         str,
            "extracted_frames": int,
            "output_dir":       str,
            "frame_interval":   int,
            "start_sec":        float,
            "end_sec":          float | None,
        }
    """
    db = _get_sync_db()
    # ── Stage 1: download ─────────────────────────────────────────────────
    self.update_state(
        state="PROGRESS",
        meta={"stage": "downloading", "percent": 0, "message": f"Downloading {filename}"},
    )

    try:
        video_path = _download_video_sync(db, owner_id, filename)
    except FileNotFoundError as exc:
        # Permanent failure — do not retry
        raise
    except Exception as exc:
        logger.warning("Download failed (%s), retrying...", [exc])
        raise self.retry(exc=exc)

    # ── Stage 2: extract frames ───────────────────────────────────────────
    output_dir = PARSED_TMP_DIR / video_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    self.update_state(
        state="PROGRESS",
        meta={"stage": "extracting", "percent": 0, "message": "Starting frame extraction"},
    )

    # Progress callback — called by parsevid.py on every saved frame.
    # update_state is cheap (one MongoDB write) so calling it per-frame
    # is fine for typical frame_interval values (every 1–5 seconds of video).
    # If frame_interval=1 on a 30fps video, throttle reporting to every 30 frames.
    _report_every = max(1, 30 // frame_interval)  # ~once per second of video
    
    def init_to_db():
        ParsedImage(ownerId=owner_id, filename=filename).insert()
    def save_to_db(frame: bytes, frame_index: int):
        image = frames(imageData=frame, frameIndex=frame_index)
        parsed_image_parent = ParsedImage.find_one({"ownerId": owner_id, "filename": filename})
        parsed_image_parent.update(Push({"imageFrames": image}))

    def on_progress(saved_count: int, total_frames: int):
        if saved_count % _report_every == 0 or saved_count == total_frames:
            percent = int(saved_count / max(total_frames, 1) * 100)
            self.update_state(
                state="PROGRESS",
                meta={
                    "stage":          "extracting",
                    "current_frame":  saved_count,
                    "total_frames":   total_frames,
                    "percent":        percent,
                    "message":        f"Extracted {saved_count}/{total_frames} frames",
                },
            )

    logger.info(
        "Extracting frames: file=%s interval=%d start=%.1f end=%s",
        video_path, frame_interval, start_sec, end_sec,
    )
    init_to_db()

    extracted_frames, out_path = video_to_frames(
        video_path=video_path,
        output_dir=output_dir,
        start_sec=start_sec,
        end_sec=end_sec,
        frame_interval=frame_interval,
        compression=9,
        on_progress=on_progress,
        save_to_db=save_to_db
    )

    logger.info("Extraction complete: %d frames → %s", extracted_frames, out_path)

    # ── Return value becomes the SUCCESS result ────────────────────────────
    return {
        "filename":         filename,
        "extracted_frames": extracted_frames,
        "output_dir":       str(out_path),
        "frame_interval":   frame_interval,
        "start_sec":        start_sec,
        "end_sec":          end_sec,
    }