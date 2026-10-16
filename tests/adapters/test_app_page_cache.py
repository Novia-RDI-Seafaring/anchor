"""The app page is fetched fresh every time; the hashed bundle may be cached.

A browser that kept an old page kept loading the old bundle after an
upgrade, so a new feature looked missing with no error anywhere.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from tests.fixtures.services import make_in_memory_services


def _client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<script src="/assets/index-abc.js"></script>')
    (tmp_path / "assets" / "index-abc.js").write_text("app()")
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace, ingest_service=s.ingest, doc_store=s.doc_store,
        bus=s.bus, intent_service=s.intents, static_dir=tmp_path,
    )
    return TestClient(app)


def test_the_app_page_is_never_served_from_cache(tmp_path):
    client = _client(tmp_path)
    for path in ("/", "/c/test", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert "index-abc.js" in response.text
        assert response.headers["cache-control"] == "no-cache", path


def test_the_bundle_keeps_ordinary_caching(tmp_path):
    response = _client(tmp_path).get("/assets/index-abc.js")
    assert response.text == "app()"
    assert "cache-control" not in response.headers
