"""
Lightweight JSONL logger for eval traces.

Each call to `log_event` appends a single JSON object to `logs/runs.jsonl`.
This is meant for instrumentation only and must not break the main flow.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
import uuid

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "runs.jsonl"

_lock = Lock()
_run_id = os.getenv("EVAL_RUN_ID", uuid.uuid4().hex)


def get_run_id() -> str:
    return _run_id


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_event(event: Dict[str, Any]) -> None:
    """
    Append a JSON line to the eval log.
    Never raise; best-effort only.
    """
    try:
        _ensure_log_dir()
        payload: Dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "run_id": get_run_id(),
            **event,
        }
        line = json.dumps(payload, default=str)
        with _lock:
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # Swallow all errors to avoid affecting runtime behavior
        return


def clear_log() -> None:
    """Convenience for tests/evals: wipe current log file."""
    try:
        if LOG_FILE.exists():
            LOG_FILE.unlink()
    except Exception:
        return
