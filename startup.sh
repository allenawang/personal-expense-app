#!/usr/bin/env bash
# Azure App Service startup command.
# Set this file as the Startup Command in Configuration > General settings.
set -e
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile '-'
