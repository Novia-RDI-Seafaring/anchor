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
