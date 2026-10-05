"""Original-source identity shared by ingestion and store adapters."""
from __future__ import annotations

import hashlib

from anchor.core.ids import validate_workspace_slug
from anchor.core.upload_safety import UnsafeUploadError


class SourceIdentityError(UnsafeUploadError):
    """Original ownership or integrity cannot be established safely."""


def original_source(pdf_bytes: bytes, slug: str) -> dict[str, str]:
    validate_workspace_slug(slug)
    return {"slug": slug, "sha256": hashlib.sha256(pdf_bytes).hexdigest()}
