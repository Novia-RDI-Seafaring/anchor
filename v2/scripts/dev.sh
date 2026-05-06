#!/usr/bin/env bash
# Run backend + Vite dev together. Assumes uv + pnpm installed.
set -euo pipefail

cd "$(dirname "$0")/.."

# Trap SIGINT so both processes die cleanly on Ctrl-C
trap 'kill 0' SIGINT SIGTERM EXIT

# Backend (FastAPI :8002 + MCP-SSE)
uv run anchor serve --data-dir ./data &

# Frontend (Vite :5173 with proxy)
pnpm --filter @anchor/web dev &

wait
