"""Construct OpenAI-compatible clients from explicit egress authority.

The environment-scoped egress policy resolves credentials and endpoints before
calling this factory. Keeping ambient credential lookup out of this low-level
module prevents a custom endpoint from inheriting an unrelated public key.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from openai import OpenAI


def make_openai_client(api_key: str | None, base_url: str | None) -> OpenAI:
    """Build a client from an explicit key and optional endpoint."""
    if not api_key:
        raise ValueError("model client construction requires an explicit API key")

    from openai import OpenAI

    kwargs: dict[str, str] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)
