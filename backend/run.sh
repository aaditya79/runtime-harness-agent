#!/usr/bin/env bash
# Helper script to launch the dev backend.
# Run from the backend/ directory:  ./run.sh
set -e
cd "$(dirname "$0")"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
