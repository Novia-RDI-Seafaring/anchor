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

_SERVER_EGRESS_PROVIDERS = frozenset({"azure", "custom", "ollama", "openai"})
#: Providers whose vision stages run through the user's own signed-in agent
#: CLI. Page content leaves the host (to Anthropic or OpenAI), so they count
#: as egress, but Anchor builds no model client and holds no credential.
AGENT_CLI_PROVIDERS = frozenset({"claude", "codex"})
_PROJECT_IMMUTABLE_FIELDS = frozenset({"openai_base_url", "provider"})
_PROJECT_FORBIDDEN_FIELDS = frozenset({"openai_api_key"})


class EgressPolicyError(ValueError):
    """Raised before runtime startup when model egress policy is unsafe."""


ANCHOR_KEY_VAR = "ANCHOR_OPENAI_API_KEY"


def credential_hint(dotenv_path: Path | str | None) -> str:
    """Where the model key goes, and why a shell export may not reach Anchor."""
    target = str(dotenv_path) if dotenv_path else "the environment's .env file next to env.toml"
    return (
        f"Set {ANCHOR_KEY_VAR} in {target}. Apps like Claude Desktop do not "
        "inherit shell variables, so a key exported in your shell is invisible to them."
    )


class MissingModelCredentialError(EgressPolicyError):
    """A remote model is configured but no key is visible to this process.

    Raised only by operations that actually call the remote model (query
    embedding, embedding at ingest). Read-only operations never raise it.
    """

    code = "missing_model_credential"

    def __init__(self, model: str, *, dotenv_path: Path | str | None = None) -> None:
        super().__init__(
            f"remote embedding model {model!r} requires an approved model "
            "credential, and none is visible to this process"
        )
        self.model = model
        self.hint = credential_hint(dotenv_path)

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": str(self), "hint": self.hint}


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    """Resolved model-client capability for one environment."""

    provider: str | None
    api_key: str | None
    base_url: str | None
    server_egress_allowed: bool
    remote_clients_enabled: bool
    credential_source: str | None = None
    dotenv_path: Path | None = None
    #: ``claude`` or ``codex`` when the vision stages run through that CLI.
    agent_cli: str | None = None

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
                f"provider {provider!r} does not allow remote embedding model "
                f"{model!r}: embedding would send document text off-host. "
                "Set embed_model to a local model (for example "
                "'hotchpotch/bekko-embedding-v1-a25m'), or move the project to an "
                "environment that allows model egress."
            )
        if require_credential and not self.remote_clients_enabled:
            raise MissingModelCredentialError(model, dotenv_path=self.dotenv_path)


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
    if provider in AGENT_CLI_PROVIDERS and not config.local_only:
        policy = EgressPolicy(
            provider=provider,
            api_key=None,
            base_url=None,
            server_egress_allowed=True,
            remote_clients_enabled=False,
            dotenv_path=environment_dotenv_path(config),
            agent_cli=provider,
        )
        # Embeddings stay on the host: there is no endpoint key to embed with.
        policy.validate_embed_model(
            config.embed_model,
            require_credential=require_remote_credential,
        )
        return policy
    server_egress_allowed = (
        not config.local_only and provider in _SERVER_EGRESS_PROVIDERS
    )
    no_server_egress = not server_egress_allowed
    if no_server_egress:
        # No server-side model egress at all (local_only, provider 'local' or
        # 'harness', or unconfigured): the server loads only cached model
        # weights, so pin HuggingFace offline. Without this a 'harness' env hits
        # huggingface.co on every model load, which slows the MCP connect path
        # and defeats the point of a no-egress posture. setdefault-based, so an
        # operator can still force a first-run download with HF_HUB_OFFLINE=0,
        # and `anchor models prefetch` never calls enforce_offline().
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
        dotenv_path=environment_dotenv_path(config),
    )
    policy.validate_embed_model(
        config.embed_model,
        require_credential=require_remote_credential,
    )
    return policy


def environment_dotenv_path(config: AnchorConfig) -> Path | None:
    """The private ``.env`` of the environment that owns ``config``'s project.

    Set by the environment resolver (``anchor.infra.environment``); ``None``
    for a config built without an environment.
    """
    return getattr(config, "_env_dotenv_path", None)


def describe_credential(config: AnchorConfig) -> dict[str, Any]:
    """Credential state for status surfaces. Never includes the key itself.

    ``source`` names where the effective key came from: ``env_file`` (the
    environment's private ``.env``) or ``process`` (the launching shell or app).
    A process-only key is invisible to apps launched outside that shell.
    """
    provider = (config.provider or "").strip().lower() or None
    # Ollama runs with a local placeholder key, so only real endpoints need one.
    required = not config.local_only and provider in _SERVER_EGRESS_PROVIDERS - {"ollama"}
    dotenv_path = environment_dotenv_path(config)
    env_file_has_key = bool(read_environment_dotenv(dotenv_path).get("openai_api_key"))
    variable: str | None = None
    source: str | None = None
    if required:
        if os.environ.get(ANCHOR_KEY_VAR, "").strip():
            variable, source = ANCHOR_KEY_VAR, "process"
        elif env_file_has_key:
            variable, source = ANCHOR_KEY_VAR, "env_file"
        elif config.openai_api_key is not None:
            variable, source = ANCHOR_KEY_VAR, "config"
        elif (
            provider == "openai"
            and not (config.openai_base_url or "").strip()
            and os.environ.get("OPENAI_API_KEY", "").strip()
        ):
            variable, source = "OPENAI_API_KEY", "process"
    info: dict[str, Any] = {
        "required": required,
        "present": source is not None,
        "source": source,
        "variable": variable,
        "env_file": str(dotenv_path) if dotenv_path is not None else None,
        "env_file_has_key": env_file_has_key,
    }
    if required and (source is None or (source == "process" and not env_file_has_key)):
        info["hint"] = credential_hint(dotenv_path)
    return info


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
