"""The activity log: one line per adapter call, in the project's data dir.

Every HTTP request and MCP tool call appends ``{ts, kind, name, ms, ...}``
to ``activity.jsonl``. One file, so the HTTP server, an MCP session and the
CLI all write to the same place and any of them can read it back. It is
what makes an agent's cost per intent measurable: not the server's
milliseconds, which are few, but the number of calls, which is the number
of turns an agent took.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILE_NAME = "activity.jsonl"


class ActivityLog:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / FILE_NAME

    def record(self, **entry: Any) -> None:
        """Append one call. Never raises: a log must not break the call."""
        entry.setdefault("ts", time.time())
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError as exc:
            # A full disk or a read-only data dir must not fail the request
            # or tool call being logged; the measurement is best effort.
            logger.debug("activity log write to %s failed: %s", self.path, exc)

    def read(self, *, since: float | None = None, limit: int = 5000) -> list[dict[str, Any]]:
        """The last ``limit`` entries at or after ``since``, oldest first."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if since is not None and float(entry.get("ts") or 0) < since:
                    continue
                out.append(entry)
        return out[-limit:]
