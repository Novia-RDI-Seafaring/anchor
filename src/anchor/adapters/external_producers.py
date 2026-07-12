"""Compose external OIP discovery with process-isolated producer gateways."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path

from anchor.adapters.extension_host import (
    ExtensionHost,
    ExtensionRuntimeStatus,
    external_registration_fingerprint,
)
from anchor.adapters.external_oip.gateway import (
    ExternalProducerGateway,
    ExternalProducerStatus,
    GatewayCatalog,
    ProducerConnector,
)


def build_external_gateway(
    data_dir: Path,
    *,
    connector: ProducerConnector | None = None,
    reserved_tool_names: Iterable[str] = (),
) -> ExternalProducerGateway:
    """Build a gateway from manifests explicitly registered for a project."""
    host = ExtensionHost(data_dir)
    bundled_names = {
        manifest["producer"]["name"] for manifest in host.bundled_manifests()
    }
    return ExternalProducerGateway(
        host.external_manifests(),
        connector=connector,
        reserved_tool_names=reserved_tool_names,
        reserved_producer_names=bundled_names,
    )


class ExternalProducerGateways:
    """Own a bounded set of project gateways for one adapter runtime."""

    def __init__(
        self,
        *,
        cache_size: int = 8,
        reserved_tool_names: Iterable[str] = (),
    ) -> None:
        self.cache_size = cache_size
        self.reserved_tool_names = set(reserved_tool_names)
        self._gateways: OrderedDict[
            str,
            tuple[tuple[tuple[str, int, int, bool, int], ...], ExternalProducerGateway],
        ] = OrderedDict()

    async def gateway_for(self, data_dir: Path) -> ExternalProducerGateway:
        key = str(Path(data_dir).resolve())
        fingerprint = external_registration_fingerprint(Path(data_dir))
        cached = self._gateways.get(key)
        if cached is None or cached[0] != fingerprint:
            if cached is not None:
                await cached[1].close()
            gateway = build_external_gateway(
                Path(data_dir),
                reserved_tool_names=self.reserved_tool_names,
            )
            self._gateways[key] = (fingerprint, gateway)
            while len(self._gateways) > self.cache_size:
                _old_key, (_fingerprint, old_gateway) = self._gateways.popitem(
                    last=False
                )
                await old_gateway.close()
        else:
            gateway = cached[1]
            self._gateways.move_to_end(key)
        return gateway

    def reserve(self, tool_names: Iterable[str]) -> None:
        """Reserve ANCHOR-owned names before any gateway is constructed."""
        if self._gateways:
            raise RuntimeError("cannot change reserved tool names after gateway startup")
        self.reserved_tool_names.update(tool_names)

    async def catalog_for(self, data_dir: Path) -> GatewayCatalog:
        return await (await self.gateway_for(data_dir)).catalog()

    async def close(self) -> None:
        for _fingerprint, gateway in self._gateways.values():
            await gateway.close()
        self._gateways.clear()


def external_statuses(
    statuses: Iterable[ExternalProducerStatus],
) -> dict[str, ExtensionRuntimeStatus]:
    """Convert external diagnostics to the shared adapter status shape."""
    return {
        status.name: ExtensionRuntimeStatus(
            name=status.name,
            source=status.source,
            available=status.available,
            reason=status.reason,
            error_type=status.error_type,
        )
        for status in statuses
    }


def external_catalog_payload(catalog: GatewayCatalog) -> dict[str, object]:
    """Return an adapter-neutral external producer catalog payload."""
    return {
        "tools": [
            {
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "input_schema": tool.inputSchema,
                "output_schema": tool.outputSchema,
            }
            for tool in catalog.tools
        ],
        "producers": [
            {
                "name": status.name,
                "source": status.source,
                "available": status.available,
                "reason": status.reason,
                "error_type": status.error_type,
                "tool_count": status.tool_count,
            }
            for status in catalog.statuses
        ],
    }
