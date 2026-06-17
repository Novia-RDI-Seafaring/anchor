"""ProjectRouter — resolve a per-call project to its service bundle (anchor#120).

One MCP server serves one *environment* (the trust boundary). Each tool call
names a *project* inside it; the router resolves ``(environment, project)`` to a
:class:`~anchor.adapters.mcp.services.ServiceBundle`, cached by the project's
storage directory, so the running server multiplexes any number of projects
without rebinding at startup. It also backs the lifecycle tools
(``create_environment`` / ``create_project`` / ``list_projects`` /
``open_project``) and raises the self-correcting ``no_project`` /
``no_environment`` errors.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from anchor.adapters.mcp.services import ServiceBundle, build_bundle
from anchor.core.ids import validate_project_name
from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    DEFAULT_PROJECT,
    Environment,
    Meta,
    NoEnvironmentError,
    NoProjectError,
    create_project,
    ensure_project,
    init_environment,
    project_meta,
    resolve_environment,
    resolve_project_config,
    set_project_description,
)


class ProjectRouter:
    """Resolve projects to cached service bundles for one environment."""

    def __init__(
        self,
        *,
        env_arg: Path | str | None = None,
        base_url: str = "http://localhost:8002",
        cache_size: int = 8,
    ) -> None:
        self.env_arg = env_arg
        self.base_url = base_url
        self.cache_size = cache_size
        self._cache: OrderedDict[str, ServiceBundle] = OrderedDict()
        self._session_default: str | None = None

    # -- environment ------------------------------------------------------- #
    def environment(self) -> Environment:
        return resolve_environment(self.env_arg)

    def _usable(self, env: Environment) -> bool:
        """An environment can host the ``default`` project when legacy/global,
        or any project once it has a real config."""
        return env.initialized or env.legacy

    def _resolve_name(self, env: Environment, project: str | None) -> str | None:
        """Per-call name > session default > implied 'default' (global/legacy)."""
        if project:
            return project
        if self._session_default:
            return self._session_default
        if env.legacy or env.root == env_mod.GLOBAL_ENV_DIR:
            return DEFAULT_PROJECT
        return None

    # -- bundles ----------------------------------------------------------- #
    def bundle_for(self, project: str | None) -> ServiceBundle:
        """Resolve ``project`` (or the implied default) to its service bundle."""
        env = self.environment()
        if not self._usable(env):
            raise NoEnvironmentError(env.root)
        name = self._resolve_name(env, project)
        if name is None:
            raise NoProjectError(None, env.list_project_names())
        validate_project_name(name)
        is_default = name == DEFAULT_PROJECT and (env.legacy or env.root == env_mod.GLOBAL_ENV_DIR)
        if is_default:
            ensure_project(env, name)  # the implied default auto-provisions
        elif not env.project_exists(name):
            raise NoProjectError(name, env.list_project_names())
        data_dir = env.project_dir(name)
        key = str(data_dir)
        bundle = self._cache.get(key)
        if bundle is None:
            config = resolve_project_config(env, name)
            bundle = build_bundle(config, base_url=self.base_url)
            self._cache[key] = bundle
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        return bundle

    # -- lifecycle --------------------------------------------------------- #
    def list_projects(self) -> dict[str, Any]:
        env = self.environment()
        projects = [
            {"name": name, "description": project_meta(env, name).description}
            for name in env.list_project_names()
        ]
        return {
            "environment": str(env.root),
            "initialized": env.initialized,
            "session_default": self._session_default,
            "projects": projects,
        }

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        env = self.environment()
        if not env.initialized:
            raise NoEnvironmentError(env.root)
        create_project(env, name, description=description)
        self._cache.pop(str(env.project_dir(name)), None)
        return {"created": name, "data_dir": str(env.project_dir(name))}

    def create_environment(
        self,
        directory: str | None = None,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        embed_model: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        root = Path(directory).expanduser() if directory else self._default_env_root()
        settings: dict[str, Any] = {}
        if provider:
            settings["provider"] = provider
        if base_url:
            settings["openai_base_url"] = base_url
        if embed_model:
            settings["embed_model"] = embed_model
        meta = Meta(description=description or "")
        env = init_environment(root, settings=settings, meta=meta)
        # Point this router at the new environment so subsequent calls resolve it.
        self.env_arg = str(env.root)
        self._cache.clear()
        return {"environment": str(env.root), "config": str(env.config_path)}

    def update_project(self, name: str, description: str) -> dict[str, Any]:
        env = self.environment()
        if not env.initialized:
            raise NoEnvironmentError(env.root)
        if not env.project_exists(name):
            raise NoProjectError(name, env.list_project_names())
        set_project_description(env, name, description)
        return {"updated": name, "description": description}

    def open_project(self, name: str) -> dict[str, Any]:
        env = self.environment()
        validate_project_name(name)
        if not env.project_exists(name):
            raise NoProjectError(name, env.list_project_names())
        self._session_default = name
        return {"session_default": name}

    def _default_env_root(self) -> Path:
        if self.env_arg:
            return Path(self.env_arg).expanduser()
        return env_mod.GLOBAL_ENV_DIR
