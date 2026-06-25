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
from openai import OpenAIError

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


def test_base_url_honored_without_key(monkeypatch):
    # A stray public key in the env must NOT pull us back to api.openai.com when
    # an endpoint is configured: the zone wins.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-personal-public")
    client = make_openai_client(None, AZURE)
    parsed = urlsplit(_base_url(client))
    assert parsed.hostname is not None and parsed.hostname.endswith(".azure.com")
    assert parsed.hostname != "api.openai.com"


def test_no_base_url_uses_default(monkeypatch):
    # provider=openai (no endpoint) keeps the public default -- intended.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-personal-public")
    client = make_openai_client(None, None)
    parsed = urlsplit(_base_url(client))
    assert parsed.hostname == "api.openai.com"


def test_missing_key_and_no_env_raises_clearly(monkeypatch):
    # No key anywhere is a clear construction error, not a silent reroute.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(OpenAIError):
        make_openai_client(None, AZURE)
