"""Provider registry invariants."""
from __future__ import annotations

from anchor.infra.providers import PROVIDERS, get_provider


def test_expected_providers_present():
    keys = {p.key for p in PROVIDERS}
    assert {"local", "ollama", "openai", "azure", "custom"} <= keys


def test_lookup_is_case_insensitive():
    assert get_provider("LOCAL").key == "local"
    assert get_provider("  Ollama ").key == "ollama"
    assert get_provider("nope") is None


def test_registry_invariants():
    for p in PROVIDERS:
        # A provider that needs an endpoint must actually use one (vision).
        if p.base_url_required:
            assert p.does_vision, p.key
        # A non-vision provider has no endpoint to require.
        if not p.does_vision:
            assert not p.base_url_required, p.key
            assert p.default_base_url is None, p.key
        # Every provider states its data zone.
        assert p.zone
