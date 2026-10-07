"""HTTP FMU routes stay in parity with their `fmu_*` MCP peers.

Regression: `GET /api/fmu/simulations` was registered after `GET
/api/fmu/{slug}`, so FastAPI resolved it as ``slug="simulations"`` and
returned 404 while the MCP peer `fmu_list_simulations` worked.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.core.clock import FixedClock
from anchor.extensions.anchor_fmus.core.services import FmuService
from anchor.extensions.anchor_fmus.infra.fake_runtime import FakeFmuRuntime
from anchor.extensions.anchor_fmus.infra.memory_store import MemoryFmuStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.services import make_in_memory_services


@pytest.fixture()
def client() -> TestClient:
    services = make_in_memory_services()
    fmu = FmuService(
        store=MemoryFmuStore(),
        runtime=FakeFmuRuntime(),
        bus=MemoryEventBus(),
        clock=FixedClock(ts=1700000000.0),
    )
    app = build_app(
        workspace_service=services.workspace,
        ingest_service=services.ingest,
        doc_store=services.doc_store,
        bus=services.bus,
        fmu_service=fmu,
    )
    app.state.fmu = fmu
    return TestClient(app)


def test_list_simulations_route_is_reachable(client):
    # Empty store: must be an empty list, never a 404 from the /{slug} route.
    response = client.get("/api/fmu/simulations")
    assert response.status_code == 200, response.text
    assert response.json() == []


async def _seed_simulation(fmu: FmuService) -> str:
    await fmu.upload_and_inspect(b"dummy-fmu", "pump.fmu")
    run = await fmu.simulate("pump")
    return run.id


def test_list_simulations_returns_seeded_run(client):
    import asyncio

    run_id = asyncio.run(_seed_simulation(client.app.state.fmu))
    listed = client.get("/api/fmu/simulations")
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [run_id]

    results = client.get(f"/api/fmu/simulations/{run_id}/results")
    assert results.status_code == 200, results.text

    # The catch-all still serves real slugs and 404s unknown ones.
    assert client.get("/api/fmu/pump").status_code == 200
    assert client.get("/api/fmu/ghost").status_code == 404
