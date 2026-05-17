# src/arq_worker/settings.py
"""
WorkerSettings is the single entry point for the Arq worker process:

    arq arq_worker.settings.WorkerSettings

on_startup runs once after each worker process starts — Motor client
and Beanie are initialised here so every task in this process can
use Beanie directly with no extra setup.

on_shutdown tears down the thread pool cleanly so in-flight CPU work
(frame extraction) can finish before the process exits.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pymongo import AsyncMongoClient
from beanie import init_beanie
from arq.connections import RedisSettings
from arq import cron
from dotenv import load_dotenv

from arq_worker.tasks.videoOps_task import upload_video, parse_video, download_parsed_frames, process_webodm_video, check_webodm_tasks
from server.common import MONGO_URI

load_dotenv()


async def startup(ctx: dict) -> None:
    from db.models import VideoUpload, ParsedImage, WebODMTask

    # Same AsyncMongoClient that FastAPI uses — Beanie 2.x supports it.
    client = AsyncMongoClient(MONGO_URI)
    db     = client[os.environ['DATABASE']]
    await init_beanie(
        database=db,
        document_models=[VideoUpload, ParsedImage, WebODMTask],
    )

    ctx["db"]           = db
    ctx["mongo_client"] = client

    # CPU-bound frame extraction runs in this pool so it never blocks
    # the asyncio event loop that drives all other task I/O.
    # max_workers=2 means at most 2 videos can be extracted in parallel
    # per worker process — tune to your CPU core count.
    ctx["executor"] = ThreadPoolExecutor(max_workers=2, thread_name_prefix="arq-cpu")

    print(f"[arq] worker started  pid={os.getpid()}")


async def shutdown(ctx: dict) -> None:
    # wait=False: don't block shutdown if a thread is still running;
    # the OS will clean up. Change to True if you need clean mid-task exits.
    if executor := ctx.get("executor"):
        executor.shutdown(wait=False)

    if client := ctx.get("mongo_client"):
        await client.close()

    print("[arq] worker stopped")


class WorkerSettings:
    functions   = [upload_video, parse_video, download_parsed_frames, process_webodm_video, check_webodm_tasks]
    cron_jobs   = [cron(check_webodm_tasks, second=0)]
    on_startup  = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
    )
    max_jobs    = 10
    job_timeout = 7_200   # 2 hours — enough for any realistic video
    keep_result = 86_400  # keep results in Redis for 24 h
    max_tries   = 3       # retry transient failures (network, GridFS blip)