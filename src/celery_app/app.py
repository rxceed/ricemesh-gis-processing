"""
src/celery_app/app.py

Single Celery application instance shared by both the FastAPI server
(for dispatching tasks) and the Celery worker process (for executing them).
Both import from here — this is the one source of truth for configuration.

Why MongoDB as result backend instead of Redis?
  MongoDB is already in the stack. Adding Redis purely for task results
  introduces a fourth service (MongoDB, RabbitMQ, FastAPI, Redis) for
  no meaningful gain. Celery's MongoDB backend stores results in
  ricemesh.celery_taskmeta — a lightweight document per task.

Task serializer: json (not pickle).
  Pickle executes arbitrary code on deserialization — a security risk if
  task arguments ever come from untrusted input. JSON is safe and
  sufficient since our task arguments are strings, ints, and floats.
"""
import os
from celery import Celery
from celery.signals import worker_process_init
from dotenv import load_dotenv
from server.common import MONGO_URI

load_dotenv()

celery_app = Celery("ricemesh", include=["celery_app.tasks.videoOps_task"])

celery_app.config_from_object({
    # ── Transport ────────────────────────────────────────────────────────
    "broker_url": os.environ["CELERY_BROKER_URL"],

    # ── Result storage ────────────────────────────────────────────────────
    # MongoDB URI — Celery appends its own collection to this database.
    "result_backend": MONGO_URI,
    "mongodb_backend_settings": {
        "database":            "ricemesh",
        "taskmeta_collection": "celery_taskmeta",
    },

    # ── Serialization ────────────────────────────────────────────────────
    "task_serializer":    "json",
    "result_serializer":  "json",
    "accept_content":     ["json"],

    # ── Reliability ──────────────────────────────────────────────────────
    # Acknowledge the message only after the task finishes (not on receipt).
    # If the worker crashes mid-task, RabbitMQ re-queues the message.
    "task_acks_late":            True,
    "task_reject_on_worker_lost": True,

    # ── Result expiry ────────────────────────────────────────────────────
    # Keep task results for 24 hours — enough for any SSE client to
    # reconnect and catch the final state.
    "result_expires": 86_400,

    # ── Routing ──────────────────────────────────────────────────────────
    # Dedicated queue for video work so CPU-heavy tasks don't starve
    # lighter tasks if more task types are added later.
    "task_routes": {
        "ricemesh.tasks.video.*": {"queue": "video_parsing"},
    },

    # ── Worker ───────────────────────────────────────────────────────────
    # Report STARTED state when a worker picks up a task.
    # Without this, state stays PENDING until the task finishes.
    "task_track_started": True,
})

@worker_process_init.connect
def init_worker(**kwargs):
    """
    This signal is caught by every child worker process when it starts.
    It ensures that the Beanie connection is ready before any task runs.
    """
    from db.models import VideoUpload, ParsedImage, frames
    from src.db.connection_bunnet import init_db, connect_client, connect_db
    import asyncio
    # Define which models Beanie should track
    # Add all your actual model classes to this list
    client = asyncio.run(connect_client(MONGO_URI))
    db = asyncio.run(connect_db(client))
    # We run the async init_beanie in the worker's current loo
    asyncio.run(init_db(db))
    
    print("Beanie initialized for Celery worker process.")

# Auto-discover tasks from the tasks subpackage
celery_app.autodiscover_tasks(["celery_app.tasks"])