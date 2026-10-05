"""The OpenAI client must always target the configured endpoint (data zone).

Regression guard for a data-boundary leak: when ``ANCHOR_OPENAI_API_KEY`` was
unset, the clients built a bare ``OpenAI()`` that dropped the configured
``base_url`` and fell back to public api.openai.com -- sending document content
out of the zone the user named. ``make_openai_client`` must forward ``base_url``
regardless of whether a key was passed.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from anchor.extensions.anchor_pdfs.infra.llm.openai_client import make_openai_client

AZURE = "https://my-resource.openai.azure.com/openai/v1/"


def _base_url(client) -> str:
    # openai>=1.0 exposes the resolved base_url; str() gives the URL.
    return str(client.base_url)


def test_base_url_honored_with_key():
    client = make_openai_client("sk-test", AZURE)
    parsed = urlsplit(_base_url(client))
    assert parsed.scheme == "https"
    assert parsed.hostname == "my-resource.openai.azure.com"


def test_configured_endpoint_rejects_ambient_public_key(monkeypatch):
    # A custom endpoint must not receive an ambient credential. Its credential
    # must be passed explicitly by the environment-scoped egress policy.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-personal-public")
    with pytest.raises(ValueError, match="explicit API key"):
        make_openai_client(None, AZURE)


def test_client_factory_does_not_resolve_ambient_public_key(monkeypatch):
    # The environment policy may deliberately select a personal public key,
    # but the low-level client factory must never resolve ambient authority.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-personal-public")
    with pytest.raises(ValueError, match="explicit API key"):
        make_openai_client(None, None)


def test_missing_key_and_no_env_raises_clearly(monkeypatch):
    # No key anywhere is a clear construction error, not a silent reroute.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="explicit API key"):
        make_openai_client(None, AZURE)
