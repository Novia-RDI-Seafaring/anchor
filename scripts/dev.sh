#!/usr/bin/env bash
# Run backend + Vite dev together. Assumes uv + pnpm installed.
set -euo pipefail

cd "$(dirname "$0")/.."

# Trap SIGINT so both processes die cleanly on Ctrl-C
trap 'kill 0' SIGINT SIGTERM EXIT

# Backend (FastAPI :8002 + browser SSE). Uses the documented default data dir.
uv run anchor serve &

# Frontend (Vite :5173 with proxy)
pnpm --dir web dev &

wait
