cd ./src
uv run celery -A celery_app.app worker \
    --loglevel=info \
    --queues=video_parsing \
    --concurrency=2       