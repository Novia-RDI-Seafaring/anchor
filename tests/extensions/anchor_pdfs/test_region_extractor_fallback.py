"""Region extractor degrades gracefully when an endpoint rejects JSON mode.

Some OpenAI-compatible endpoints (older Azure deployments, some local servers)
reject response_format=json_object. The extractor must retry without it rather
than fail gold extraction.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor


class _Msg:
    content = '{"regions": [{"id": "r1", "kind": "table"}]}'


class _Rsp:
    choices = [type("C", (), {"message": _Msg()})()]


def _client_factory(create_fn):
    class _Client:
        def __init__(self, *a, **k):
            self.chat = type("Chat", (), {"completions": type("Cmp", (), {"create": create_fn})()})()

    return _Client


def test_retries_without_json_mode_when_response_format_rejected(monkeypatch):
    calls = []

    def create(self, **kwargs):
        calls.append("response_format" in kwargs)
        if "response_format" in kwargs:
            raise RuntimeError("400 - response_format is not supported by this deployment")
        return _Rsp()

    monkeypatch.setattr("openai.OpenAI", _client_factory(create))
    rx = OpenAIRegionExtractor(api_key="x", base_url="https://r.openai.azure.com/openai/v1/")
    regions = rx._sync(b"img", 1, [], "my-deployment")
    assert regions == [{"id": "r1", "kind": "table"}]
    assert calls == [True, False]  # JSON mode first, then retried without it


def test_non_param_error_is_not_swallowed(monkeypatch):
    def create(self, **kwargs):
        raise RuntimeError("Connection refused")  # not a 400 / param problem

    monkeypatch.setattr("openai.OpenAI", _client_factory(create))
    rx = OpenAIRegionExtractor(api_key="x")
    with pytest.raises(RuntimeError, match="Connection refused"):
        rx._sync(b"img", 1, [], "model")
