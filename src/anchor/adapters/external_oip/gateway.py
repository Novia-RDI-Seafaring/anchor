"""Deep gateway for registered external OIP producer processes.

The gateway owns manifest execution policy, namespace isolation, lazy client
lifecycle, catalog caching, call routing, and failure reporting. It never
imports producer code. A transport adapter starts each registered producer in
its own process and communicates through MCP.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from mcp.types import CallToolResult, Tool

Manifest = Mapping[str, Any]
_NAMESPACE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class ExternalProducerError(RuntimeError):
    """Base error for external producer execution."""


class ExternalToolNotFoundError(ExternalProducerError):
    """Raised when a proxied tool name is not in the external catalog."""


@dataclass(frozen=True)
class ProducerSpec:
    """Validated executable contract for one registered producer."""

    name: str
    namespace: str
    command: str
    args: tuple[str, ...]
    source: str
    manifest_path: str | None = None


@dataclass(frozen=True)
class ExternalProducerStatus:
    name: str
    source: str
    available: bool
    reason: str | None = None
    error_type: str | None = None
    tool_count: int = 0


@dataclass(frozen=True)
class GatewayCatalog:
    tools: tuple[Tool, ...]
    statuses: tuple[ExternalProducerStatus, ...]


class ProducerClient(Protocol):
    async def list_tools(self) -> list[Tool]: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult: ...

    async def close(self) -> None: ...


ProducerConnector = Callable[[ProducerSpec], Awaitable[ProducerClient]]


@dataclass(frozen=True)
class _ToolRoute:
    producer_name: str
    remote_name: str


class ExternalProducerGateway:
    """Catalog and call registered external producers through one interface."""

    def __init__(
        self,
        manifests: Sequence[Manifest],
        *,
        connector: ProducerConnector | None = None,
        reserved_tool_names: Iterable[str] = (),
        reserved_producer_names: Iterable[str] = (),
    ) -> None:
        self._connector = connector or _default_connector
        self._specs: dict[str, ProducerSpec] = {}
        self._statuses: dict[str, ExternalProducerStatus] = {}
        self._clients: dict[str, ProducerClient] = {}
        self._tools: dict[str, Tool] = {}
        self._routes: dict[str, _ToolRoute] = {}
        self._cataloged = False
        self._reserved_tool_names = frozenset(reserved_tool_names)
        self._reserved_producer_names = frozenset(reserved_producer_names)
        self._known_namespaces: set[str] = set()
        self._load_specs(manifests)

    @property
    def producer_count(self) -> int:
        return len(self._statuses)

    def can_handle(self, exposed_name: str) -> bool:
        """Return whether the tool uses a valid registered namespace."""
        namespace, separator, _remote_name = exposed_name.partition(".")
        return bool(separator) and namespace in self._known_namespaces

    async def catalog(self, *, refresh: bool = False) -> GatewayCatalog:
        """Return namespaced tools and per-producer runtime diagnostics."""
        if self._cataloged and not refresh:
            return self._snapshot()
        if refresh:
            await self._close_clients()

        self._tools.clear()
        self._routes.clear()
        for spec in sorted(self._specs.values(), key=lambda item: item.name):
            try:
                client = await self._client_for(spec)
                remote_tools = await client.list_tools()
                for remote_tool in remote_tools:
                    exposed_name = f"{spec.namespace}.{remote_tool.name}"
                    if exposed_name in self._reserved_tool_names:
                        raise ExternalProducerError(
                            f"external tool conflicts with an ANCHOR tool: {exposed_name}"
                        )
                    if exposed_name in self._routes:
                        raise ExternalProducerError(
                            f"duplicate external tool name: {exposed_name}"
                        )
                    self._tools[exposed_name] = remote_tool.model_copy(
                        update={"name": exposed_name}
                    )
                    self._routes[exposed_name] = _ToolRoute(
                        producer_name=spec.name,
                        remote_name=remote_tool.name,
                    )
                self._statuses[spec.name] = ExternalProducerStatus(
                    name=spec.name,
                    source=spec.source,
                    available=True,
                    tool_count=len(remote_tools),
                )
            except Exception as exc:  # noqa: BLE001 - isolate one producer
                await self._discard_client(spec.name)
                self._remove_routes_for(spec.name)
                self._statuses[spec.name] = ExternalProducerStatus(
                    name=spec.name,
                    source=spec.source,
                    available=False,
                    reason=str(exc),
                    error_type=exc.__class__.__name__,
                )
        self._cataloged = True
        return self._snapshot()

    async def call(
        self,
        exposed_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> CallToolResult:
        """Call one namespaced external tool with unchanged MCP content."""
        if not self._cataloged:
            await self.catalog()
        route = self._routes.get(exposed_name)
        if route is None:
            raise ExternalToolNotFoundError(
                f"external tool is unavailable or unknown: {exposed_name}"
            )
        spec = self._specs[route.producer_name]
        try:
            client = await self._client_for(spec)
            return await client.call_tool(route.remote_name, dict(arguments or {}))
        except Exception as exc:
            await self._discard_client(spec.name)
            self._remove_routes_for(spec.name)
            self._statuses[spec.name] = ExternalProducerStatus(
                name=spec.name,
                source=spec.source,
                available=False,
                reason=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise ExternalProducerError(
                f"external producer {spec.name!r} failed: {exc}"
            ) from exc

    async def close(self) -> None:
        """Stop every producer process owned by this gateway."""
        await self._close_clients()
        self._cataloged = False
        self._tools.clear()
        self._routes.clear()

    def _load_specs(self, manifests: Sequence[Manifest]) -> None:
        namespace_owners: dict[str, list[str]] = {}
        for manifest in manifests:
            name = _producer_name(manifest)
            source = str(manifest.get("_anchor_source", "registered"))
            invocation = manifest.get("invocation")
            if isinstance(invocation, Mapping):
                namespace = invocation.get("tools_namespace")
                if isinstance(namespace, str) and _NAMESPACE_RE.fullmatch(namespace):
                    self._known_namespaces.add(namespace)
            if name in self._reserved_producer_names:
                self._statuses[name] = ExternalProducerStatus(
                    name=name,
                    source=source,
                    available=False,
                    reason=f"external producer conflicts with bundled producer: {name}",
                    error_type="ProducerNameCollisionError",
                )
                continue
            try:
                spec = _producer_spec(manifest, name=name, source=source)
            except Exception as exc:
                self._statuses[name] = ExternalProducerStatus(
                    name=name,
                    source=source,
                    available=False,
                    reason=str(exc),
                    error_type=exc.__class__.__name__,
                )
                continue
            self._specs[name] = spec
            self._statuses[name] = ExternalProducerStatus(
                name=name,
                source=source,
                available=False,
                reason="not started",
            )
            namespace_owners.setdefault(spec.namespace, []).append(name)

        for namespace, owners in namespace_owners.items():
            if len(owners) < 2:
                continue
            reason = (
                f"tools_namespace {namespace!r} is claimed by: "
                + ", ".join(sorted(owners))
            )
            for name in owners:
                spec = self._specs.pop(name)
                self._statuses[name] = ExternalProducerStatus(
                    name=name,
                    source=spec.source,
                    available=False,
                    reason=reason,
                    error_type="NamespaceCollisionError",
                )

    async def _client_for(self, spec: ProducerSpec) -> ProducerClient:
        client = self._clients.get(spec.name)
        if client is None:
            client = await self._connector(spec)
            self._clients[spec.name] = client
        return client

    async def _discard_client(self, producer_name: str) -> None:
        client = self._clients.pop(producer_name, None)
        if client is not None:
            try:
                await client.close()
            except Exception:  # noqa: BLE001 - failure already captured
                pass

    async def _close_clients(self) -> None:
        for name in list(self._clients):
            await self._discard_client(name)

    def _remove_routes_for(self, producer_name: str) -> None:
        removed = [
            name
            for name, route in self._routes.items()
            if route.producer_name == producer_name
        ]
        for name in removed:
            self._routes.pop(name, None)
            self._tools.pop(name, None)

    def _snapshot(self) -> GatewayCatalog:
        return GatewayCatalog(
            tools=tuple(self._tools[name] for name in sorted(self._tools)),
            statuses=tuple(
                self._statuses[name] for name in sorted(self._statuses)
            ),
        )


def _producer_name(manifest: Manifest) -> str:
    producer = manifest.get("producer")
    if isinstance(producer, Mapping):
        name = producer.get("name")
        if isinstance(name, str) and name:
            return name
    return "unknown-producer"


def _producer_spec(manifest: Manifest, *, name: str, source: str) -> ProducerSpec:
    if manifest.get("_anchor_execution_enabled") is not True:
        raise ValueError(
            "execution is not enabled; run `anchor extensions enable "
            f"{name} --scope {source}`"
        )
    invocation = manifest.get("invocation")
    if not isinstance(invocation, Mapping):
        raise ValueError("invocation must be an object")
    if invocation.get("kind") != "mcp-stdio":
        raise ValueError("only invocation.kind='mcp-stdio' is executable")
    command = invocation.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("invocation.command must be a non-empty string")
    args = invocation.get("args", [])
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError("invocation.args must be an array of strings")
    namespace = invocation.get("tools_namespace")
    if not isinstance(namespace, str) or not _NAMESPACE_RE.fullmatch(namespace):
        raise ValueError(
            "invocation.tools_namespace must start with a letter and contain "
            "only letters, digits, underscores, or hyphens"
        )
    return ProducerSpec(
        name=name,
        namespace=namespace,
        command=command,
        args=tuple(args),
        source=source,
        manifest_path=_optional_string(manifest.get("_manifest_path")),
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


async def _default_connector(spec: ProducerSpec) -> ProducerClient:
    from anchor.adapters.external_oip.mcp_stdio import connect_mcp_stdio

    return await connect_mcp_stdio(spec)
