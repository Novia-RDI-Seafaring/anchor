"""Anchor filesystem-store exception compatibility."""
from pathlib import Path

from anchor.core.upload_safety import UnsafeUploadError
from intent_layer.fs_store import FsIntentStore as ThreadFsIntentStore


class FsIntentStore(ThreadFsIntentStore):
    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir, unsafe_id_error=UnsafeUploadError)
