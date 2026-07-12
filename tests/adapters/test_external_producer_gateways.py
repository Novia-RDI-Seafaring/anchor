"""Project gateway cache and registration refresh tests."""

from __future__ import annotations

import pytest

from anchor.adapters import external_producers
from anchor.adapters.external_producers import ExternalProducerGateways


class FakeGateway:
    def __init__(self, number: int) -> None:
        self.number = number
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_registration_change_rebuilds_only_affected_project(
    tmp_path, monkeypatch
):
    fingerprint = [("manifest", 1, 1, False, 0)]
    built: list[FakeGateway] = []

    monkeypatch.setattr(
        external_producers,
        "external_registration_fingerprint",
        lambda _data_dir: tuple(fingerprint),
    )

    def build(_data_dir, *, reserved_tool_names):
        gateway = FakeGateway(len(built) + 1)
        built.append(gateway)
        return gateway

    monkeypatch.setattr(external_producers, "build_external_gateway", build)
    registry = ExternalProducerGateways()

    first = await registry.gateway_for(tmp_path)
    unchanged = await registry.gateway_for(tmp_path)
    fingerprint[0] = ("manifest", 2, 1, True, 2)
    refreshed = await registry.gateway_for(tmp_path)

    assert unchanged is first
    assert refreshed is not first
    assert first.closed is True
    assert len(built) == 2
    await registry.close()
    assert refreshed.closed is True
