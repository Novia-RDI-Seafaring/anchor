"""Atomic replacement with bounded handling of Windows sharing denials."""
from __future__ import annotations

import os
import sys
from asyncio import sleep
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"
_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16)


async def replace_file(source: Path, destination: Path) -> None:
    """Replace a staged file without deleting or truncating its destination.

    Windows can report access denied while a short-lived reader holds the
    destination open without delete sharing. Retry only that demonstrated
    error, yielding between attempts for at most 310 ms of retry waits.
    Permanent failures retain their exception; callers own temp-file cleanup.
    """
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            if (
                not _IS_WINDOWS
                or getattr(error, "winerror", None) != 5
                or attempt == len(_RETRY_DELAYS)
            ):
                raise
            await sleep(_RETRY_DELAYS[attempt])
