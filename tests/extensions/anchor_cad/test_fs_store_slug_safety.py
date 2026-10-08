"""FsCadStore refuses traversal slugs (CodeQL py/path-injection).

`artefacts/<slug>/model.json` is built from an HTTP / MCP / CLI argument.
A malformed slug can never name a stored model, so reads report "not found"
and keep `GET /api/cad/{slug}` answering 404 as before.
"""
from __future__ import annotations

import pytest

from anchor.core.upload_safety import UnsafeUploadError
from anchor.extensions.anchor_cad.infra.fs_store import FsCadStore


@pytest.mark.parametrize("slug", ["../x", "..", ".", "a/b", "a\\b", ""])
def test_model_path_rejects_traversal_slugs(tmp_path, slug):
    with pytest.raises(UnsafeUploadError):
        FsCadStore(tmp_path)._model_path(slug)


@pytest.mark.parametrize("slug", ["../x", "..", "a/b"])
async def test_get_model_reports_not_found_for_traversal_slugs(tmp_path, slug):
    # A model.json planted one level above artefacts/ must stay unreachable.
    (tmp_path / "cad" / "model.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cad" / "model.json").write_text("{}", encoding="utf-8")
    assert await FsCadStore(tmp_path).get_model(slug) is None


def test_model_path_resolves_a_normal_slug(tmp_path):
    store = FsCadStore(tmp_path)
    assert store._model_path("pump-housing").parts[-2:] == ("pump-housing", "model.json")
