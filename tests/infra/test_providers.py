"""Provider registry invariants."""
from __future__ import annotations

from anchor.infra.providers import PROVIDERS, embed_options_for, get_provider


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


def test_embed_options_depend_on_provider():
    # Local/Ollama: only the on-host model, no remote egress offered.
    for key in ("local", "ollama"):
        opts = embed_options_for(get_provider(key))
        assert len(opts) == 1
        assert all(not o.remote for o in opts)
    # Endpoint providers also offer remote embeddings.
    for key in ("openai", "azure", "custom"):
        opts = embed_options_for(get_provider(key))
        assert any(o.remote for o in opts)
        assert any(not o.remote for o in opts)
        # The local, no-egress option is first (the default).
        assert opts[0].remote is False
