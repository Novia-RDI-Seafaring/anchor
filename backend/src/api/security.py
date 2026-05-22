"""Small request guards for write-capable API routes."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status

from src.core.config import get_settings

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_loopback_request(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    return client_host in _LOOPBACK_HOSTS


async def require_write_access(
    request: Request,
    x_anchor_write_key: str | None = Header(default=None),
) -> None:
    """Require a write API key unless local unsafe writes are explicitly allowed."""
    settings = get_settings()
    expected_key = settings.anchor_write_api_key.strip()

    if expected_key:
        if x_anchor_write_key and secrets.compare_digest(x_anchor_write_key, expected_key):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid write API key",
        )

    if settings.allow_unsafe_local_writes and _is_loopback_request(request):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Write API key is required for this route",
    )
