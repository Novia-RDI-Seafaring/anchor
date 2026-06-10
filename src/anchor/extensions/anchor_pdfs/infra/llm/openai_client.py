"""Shared OpenAI client construction for the PDF polish / region / embed stages.

Centralising this guarantees the configured ``base_url`` (the data zone the user
named in ``anchor init``) is ALWAYS honoured. The previous per-call idiom

    OpenAI(api_key=key, base_url=url) if key else OpenAI()

silently dropped ``base_url`` whenever ``ANCHOR_OPENAI_API_KEY`` was unset: the
bare ``OpenAI()`` then fell back to ``OPENAI_API_KEY`` and the public
``api.openai.com``. For an Azure/custom project that means document content the
user believed was confined to their own endpoint would instead be sent to public
OpenAI — a data-boundary violation. Always passing ``base_url`` keeps egress in
the configured zone; a missing key surfaces as a clear auth error from that
endpoint instead of a silent reroute.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from openai import OpenAI


def make_openai_client(api_key: str | None, base_url: str | None) -> OpenAI:
    """Build an OpenAI client that always targets ``base_url`` when one is set.

    ``api_key`` may be ``None`` (the SDK then reads ``OPENAI_API_KEY`` from the
    environment); ``base_url`` is forwarded whenever present so the call lands on
    the configured endpoint rather than the public default.
    """
    from openai import OpenAI

    kwargs: dict[str, str] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)
