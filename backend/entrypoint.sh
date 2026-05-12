#!/usr/bin/env bash
set -e

mkdir -p /app/data /app/data/chroma_db

if [ ! -L /app/chroma_db ]; then
  rm -rf /app/chroma_db
  ln -s /app/data/chroma_db /app/chroma_db
fi

exec uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --timeout-keep-alive 300
