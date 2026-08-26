"""Fail-closed model egress policy for one Anchor environment.

The environment is the trust boundary. Projects may select data and canvas
state, but they must not redirect model traffic or weaken a local-only policy.
Runtime composition resolves this policy before constructing any model client.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anchor.infra.config import AnchorConfig

_NO_SERVER_EGRESS_PROVIDERS = frozenset({"harness", "local"})
_SERVER_EGRESS_PROVIDERS = frozenset({"azure", "custom", "ollama", "openai"})
_PROJECT_IMMUTABLE_FIELDS = frozenset({"openai_base_url", "provider"})
_PROJECT_FORBIDDEN_FIELDS = frozenset({"openai_api_key"})


class EgressPolicyError(ValueError):
    """Raised before runtime startup when model egress policy is unsafe."""


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    """Resolved model-client capability for one environment."""

    provider: str | None
    api_key: str | None
    base_url: str | None
    server_egress_allowed: bool
    remote_clients_enabled: bool
    credential_source: str | None = None

    def validate_embed_model(
        self,
        model: str,
        *,
        require_credential: bool = True,
    ) -> None:
        """Reject a remote embedder when this environment has no egress capability."""
        if not is_remote_embedding_model(model):
            return
        provider = self.provider or "unconfigured"
        if not self.server_egress_allowed:
            raise EgressPolicyError(
                f"provider {provider!r} does not allow remote embedding model {model!r}"
            )
        if require_credential and not self.remote_clients_enabled:
            raise EgressPolicyError(
                f"remote embedding model {model!r} requires an approved model credential"
            )


def is_remote_embedding_model(model: str) -> bool:
    """Return whether the configured embedding adapter sends text remotely."""
    return model.strip().lower().startswith("text-embedding-")


def _setting_enabled(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "on", "true", "yes"}
    return bool(value)


def read_environment_dotenv(path: Path | None) -> dict[str, str]:
    """Read an environment's private Anchor settings without global mutation."""
    if path is None or not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("ANCHOR_"):
            values[key.removeprefix("ANCHOR_").lower()] = value.strip()
    return values


def resolve_egress_policy(
    config: AnchorConfig,
    *,
    require_remote_credential: bool = True,
) -> EgressPolicy:
    """Resolve explicit model credentials and endpoint without ambient fallback."""
    provider = (config.provider or "").strip().lower() or None
    server_egress_allowed = (
        not config.local_only and provider in _SERVER_EGRESS_PROVIDERS
    )
    no_server_egress = not server_egress_allowed
    if no_server_egress:
        if config.local_only or provider == "local":
            from anchor.infra.models import enforce_offline

            enforce_offline()
        policy = EgressPolicy(
            provider=provider,
            api_key=None,
            base_url=None,
            server_egress_allowed=False,
            remote_clients_enabled=False,
        )
        policy.validate_embed_model(
            config.embed_model,
            require_credential=require_remote_credential,
        )
        return policy

    configured_key = (
        config.openai_api_key.get_secret_value() if config.openai_api_key else None
    )
    base_url = (config.openai_base_url or "").strip() or None
    if provider in {"azure", "custom", "ollama"} and base_url is None:
        raise EgressPolicyError(
            f"provider {provider!r} requires an explicit model endpoint"
        )
    api_key = configured_key
    credential_source = "anchor" if configured_key else None

    if provider == "openai" and base_url is None and api_key is None:
        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip() or None
        credential_source = "openai" if api_key else None
    elif provider == "ollama" and base_url is not None and api_key is None:
        # The SDK requires a non-empty key even though Ollama ignores it.
        api_key = "anchor-local-ollama"
        credential_source = "local-placeholder"

    policy = EgressPolicy(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        server_egress_allowed=True,
        remote_clients_enabled=api_key is not None,
        credential_source=credential_source,
    )
    policy.validate_embed_model(
        config.embed_model,
        require_credential=require_remote_credential,
    )
    return policy


def secure_environment_layers(
    environment_values: dict[str, Any],
    project_values: dict[str, Any],
) -> dict[str, Any]:
    """Return merged layers while preserving the environment's egress policy."""
    environment = dict(environment_values)
    project = dict(project_values)
    provider = str(environment.get("provider") or "").strip().lower()
    if provider == "local":
        environment["local_only"] = True

    if _setting_enabled(environment.get("local_only")) and project.get("local_only") is False:
        raise EgressPolicyError("project cannot weaken an environment's local-only policy")

    for field in _PROJECT_FORBIDDEN_FIELDS:
        if field in project:
            raise EgressPolicyError(
                f"project cannot define environment credential {field!r}"
            )

    for field in _PROJECT_IMMUTABLE_FIELDS:
        if field in project and project[field] != environment.get(field):
            raise EgressPolicyError(
                f"project cannot override environment egress field {field!r}"
            )

    environment.update(project)
    return environment


def validate_environment_config(
    environment_values: dict[str, Any],
    config: AnchorConfig,
) -> None:
    """Reject process-level overrides that redirect a named environment."""
    provider = str(environment_values.get("provider") or "").strip().lower() or None
    effective_provider = (config.provider or "").strip().lower() or None
    if provider is not None and effective_provider != provider:
        raise EgressPolicyError(
            f"process configuration cannot change environment provider {provider!r}"
        )

    environment_base_url = (
        str(environment_values.get("openai_base_url") or "").strip() or None
    )
    effective_base_url = (config.openai_base_url or "").strip() or None
    if environment_base_url != effective_base_url:
        raise EgressPolicyError("process configuration cannot redirect the environment endpoint")

    environment_local_only = (
        _setting_enabled(environment_values.get("local_only")) or provider == "local"
    )
    if environment_local_only and not config.local_only:
        raise EgressPolicyError(
            "process configuration cannot weaken an environment's local-only policy"
        )

    resolve_egress_policy(config, require_remote_credential=False)
