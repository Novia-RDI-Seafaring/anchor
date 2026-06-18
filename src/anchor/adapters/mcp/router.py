"""ProjectRouter — resolve a per-call project to its service bundle.

One MCP server serves one *environment* (a named profile = the trust boundary).
Each tool call names a *project* contained in that environment; the router
resolves it to a :class:`~anchor.adapters.mcp.services.ServiceBundle`, cached by
the project's storage directory, so the running server multiplexes any number
of projects without rebinding at startup. It also backs the lifecycle tools
(``create_environment`` / ``create_project`` / ``list_projects`` /
``open_project`` / ``update_project``) and raises the self-correcting
``no_project`` / ``no_environment`` errors.

Crossing environments is deliberately *not* an MCP operation: the agent must
not move a corpus across a trust boundary. ``anchor project move`` is the
human/CLI path for that.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from anchor.adapters.mcp.services import ServiceBundle, build_bundle
from anchor.core.ids import validate_project_name
from anchor.infra.environment import (
    DEFAULT_ENV,
    DEFAULT_PROJECT,
    Environment,
    Meta,
    NoEnvironmentError,
    NoProjectError,
    create_env,
    create_project,
    ensure_project,
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
        env_arg: str | None = None,
        base_url: str = "http://localhost:8002",
        cache_size: int = 8,
    ) -> None:
        self.env_arg = env_arg  # the environment NAME this server is pinned to
        self.base_url = base_url
        self.cache_size = cache_size
        self._cache: OrderedDict[str, ServiceBundle] = OrderedDict()
        self._session_default: str | None = None

    # -- environment ------------------------------------------------------- #
    def environment(self) -> Environment:
        return resolve_environment(self.env_arg)

    def _resolve_name(self, project: str | None) -> str:
        """Per-call name > session default > the environment's default project."""
        return project or self._session_default or DEFAULT_PROJECT

    # -- bundles ----------------------------------------------------------- #
    def bundle_for(self, project: str | None) -> ServiceBundle:
        """Resolve ``project`` (or the default) to its service bundle."""
        env = self.environment()
        name = self._resolve_name(project)
        validate_project_name(name)
        is_default = name == DEFAULT_PROJECT
        if env.initialized:
            if is_default:
                ensure_project(env, name)
            elif not env.project_exists(name):
                raise NoProjectError(name, env.list_project_names())
        else:
            # An un-initialized environment serves only the default env's
            # back-compat default project (today's ~/anchor-data); anything
            # else needs a real environment first.
            if not (env.name == DEFAULT_ENV and is_default and env.project_exists(DEFAULT_PROJECT)):
                raise NoEnvironmentError(env.name)
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
            "environment": env.name,
            "initialized": env.initialized,
            "session_default": self._session_default,
            "projects": projects,
        }

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        env = self.environment()
        if not env.initialized:
            raise NoEnvironmentError(env.name)
        create_project(env, name, description=description)
        self._cache.pop(str(env.project_dir(name)), None)
        return {"created": name, "data_dir": str(env.project_dir(name))}

    def update_project(self, name: str, description: str) -> dict[str, Any]:
        env = self.environment()
        if not env.initialized:
            raise NoEnvironmentError(env.name)
        if not env.project_exists(name):
            raise NoProjectError(name, env.list_project_names())
        set_project_description(env, name, description)
        return {"updated": name, "description": description}

    def create_environment(
        self,
        name: str | None = None,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        embed_model: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        env_name = name or self.env_arg or DEFAULT_ENV
        settings: dict[str, Any] = {}
        if provider:
            settings["provider"] = provider
        if base_url:
            settings["openai_base_url"] = base_url
        if embed_model:
            settings["embed_model"] = embed_model
        meta = Meta(description=description or "")
        env = create_env(env_name, settings=settings, meta=meta)
        # Pin this server at the created environment for subsequent calls.
        self.env_arg = env.name
        self._cache.clear()
        return {"environment": env.name, "config": str(env.config_path)}

    def open_project(self, name: str) -> dict[str, Any]:
        env = self.environment()
        validate_project_name(name)
        if not env.project_exists(name):
            raise NoProjectError(name, env.list_project_names())
        self._session_default = name
        return {"session_default": name}
