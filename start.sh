#!/usr/bin/env bash

# Default port if not set
PORT="${PORT:-8080}"

# Create temp directory if it doesn't exist
mkdir -p temp_uploads

# Start the server with Gunicorn and Uvicorn workers
exec gunicorn api:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:$PORT" \
    --timeout 300
