from __future__ import annotations

import pytest

from anchor.infra.config import AnchorConfig
from anchor.infra.egress_policy import EgressPolicyError, resolve_egress_policy


@pytest.mark.parametrize("provider", ["local", "harness"])
def test_no_server_egress_providers_ignore_all_credentials(
    tmp_path,
    monkeypatch,
    provider,
):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")
    config = AnchorConfig(
        data_dir=tmp_path,
        provider=provider,
        openai_api_key="environment-key",
        openai_base_url="https://untrusted.example/v1",
        _env_file=None,
    )

    policy = resolve_egress_policy(config)

    assert policy.remote_clients_enabled is False
    assert policy.server_egress_allowed is False
    assert policy.api_key is None
    assert policy.base_url is None


def test_public_openai_may_select_ambient_public_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")
    config = AnchorConfig(data_dir=tmp_path, provider="openai", _env_file=None)

    policy = resolve_egress_policy(config)

    assert policy.remote_clients_enabled is True
    assert policy.api_key == "ambient-public-key"
    assert policy.base_url is None
    assert policy.credential_source == "openai"


def test_custom_endpoint_requires_environment_scoped_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")
    config = AnchorConfig(
        data_dir=tmp_path,
        provider="custom",
        openai_base_url="https://models.example/v1",
        embed_model="text-embedding-3-small",
        _env_file=None,
    )

    with pytest.raises(EgressPolicyError, match="requires an approved model credential"):
        resolve_egress_policy(config)


def test_non_public_provider_requires_explicit_endpoint(tmp_path):
    config = AnchorConfig(
        data_dir=tmp_path,
        provider="custom",
        openai_api_key="environment-key",
        _env_file=None,
    )

    with pytest.raises(EgressPolicyError, match="requires an explicit model endpoint"):
        resolve_egress_policy(config)


def test_custom_endpoint_uses_explicit_environment_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")
    config = AnchorConfig(
        data_dir=tmp_path,
        provider="custom",
        openai_api_key="environment-key",
        openai_base_url="https://models.example/v1",
        _env_file=None,
    )

    policy = resolve_egress_policy(config)

    assert policy.remote_clients_enabled is True
    assert policy.api_key == "environment-key"
    assert policy.base_url == "https://models.example/v1"
    assert policy.credential_source == "anchor"


def test_ollama_uses_local_sdk_placeholder(tmp_path):
    config = AnchorConfig(
        data_dir=tmp_path,
        provider="ollama",
        openai_base_url="http://localhost:11434/v1",
        _env_file=None,
    )

    policy = resolve_egress_policy(config)

    assert policy.remote_clients_enabled is True
    assert policy.api_key == "anchor-local-ollama"
    assert policy.credential_source == "local-placeholder"


@pytest.mark.parametrize("provider", ["local", "harness", None])
def test_no_server_egress_pins_huggingface_offline(tmp_path, monkeypatch, provider):
    # A no-server-egress env loads only cached model weights; resolution pins
    # HF offline so a model load never reaches huggingface.co. Previously only
    # local_only / provider 'local' did this, so a 'harness' env still hit the
    # hub on every load.
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.delenv(var, raising=False)
    config = AnchorConfig(data_dir=tmp_path, provider=provider, _env_file=None)

    resolve_egress_policy(config)

    import os

    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"


def test_no_server_egress_offline_pin_respects_operator_optout(tmp_path, monkeypatch):
    # enforce_offline() is setdefault-based: an operator who wants a first-run
    # download sets HF_HUB_OFFLINE=0 and resolution must not clobber it.
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    config = AnchorConfig(data_dir=tmp_path, provider="harness", _env_file=None)

    resolve_egress_policy(config)

    import os

    assert os.environ.get("HF_HUB_OFFLINE") == "0"


def test_server_egress_provider_does_not_pin_offline(tmp_path, monkeypatch):
    # A provider that CAN egress from the server may legitimately fetch weights;
    # resolution must not force offline on it.
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.delenv(var, raising=False)
    config = AnchorConfig(
        data_dir=tmp_path, provider="openai", openai_api_key="k", _env_file=None
    )

    resolve_egress_policy(config)

    import os

    assert "HF_HUB_OFFLINE" not in os.environ


def test_local_only_refuses_remote_embed_model(tmp_path, monkeypatch):
    # #271: local_only is a no-egress guarantee. A remote text-embedding-*
    # embed_model would send document text to the endpoint (via an ambient
    # OPENAI_API_KEY, even with no configured key), so policy resolution must
    # refuse it loudly, naming the setting.
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")
    config = AnchorConfig(
        data_dir=tmp_path,
        provider="openai",
        local_only=True,
        embed_model="text-embedding-3-small",
        _env_file=None,
    )

    with pytest.raises(EgressPolicyError, match="does not allow remote embedding"):
        resolve_egress_policy(config)
