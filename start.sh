#!/usr/bin/env bash
PORT=${PORT:-5000}
exec uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1