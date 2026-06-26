"""Tiered MCP tool surface (anchor#133).

A base PDF+canvas project must advertise the small core, not the full ~50.
Gated extension tools stay reachable -- not advertised until the resolved
project has data for them, and always discoverable via
``anchor_list_capabilities``. Dispatch routes by name regardless of
advertisement, so a gated tool still runs when called.
"""
from __future__ import annotations

import json

import pytest
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ListToolsRequest,
)

from anchor.adapters.mcp import tiering
from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.mcp.services import build_bundle
from anchor.infra import environment as env_mod
from anchor.infra.config import AnchorConfig
from anchor.infra.environment import create_env, create_project

_CLEAR = ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR")


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy")


async def _advertised(server) -> list[str]:
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    return sorted(t.name for t in result.root.tools)


async def _call(server, name: str, _args: dict | None = None, **arguments) -> str:
    handler = server.request_handlers[CallToolRequest]
    # ``_args`` lets a tool take its own ``name`` argument (e.g. remove_project)
    # without colliding with the tool name; kwargs remain the common path.
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=_args or arguments),
    )
    result = await handler(req)
    return result.root.content[0].text


def _single_project_server(tmp_path):
    bundle = build_bundle(AnchorConfig(data_dir=tmp_path / "data"))
    return build_mcp_server(bundle=bundle), bundle


def _multiproject_server():
    router = ProjectRouter(env_arg="local")
    return build_mcp_server(router=router), router


# -- core surface ------------------------------------------------------------ #
async def test_base_single_project_advertises_core_not_full_surface(tmp_path):
    server, _ = _single_project_server(tmp_path)
    names = await _advertised(server)
    # The full dispatchable surface is ~45+; the tiered default stays a small
    # curated slice (~20, the 90% path + extract_pointed from #132).
    assert len(names) <= 21
    assert set(names) == set(tiering.CORE_NAMES) - tiering.CORE_LIFECYCLE_NAMES
    # No lifecycle tools in single-project mode.
    assert "create_environment" not in names


async def test_base_multiproject_advertises_core_plus_lifecycle(tmp_path):
    create_env("local")
    server, _ = _multiproject_server()
    names = await _advertised(server)
    assert len(names) <= 21
    assert tiering.CORE_NAMES.issubset(set(names))
    # The long tail is gated out by default.
    for gated in ("fmu_inspect", "inspect", "sysml_render", "create_environment",
                  "get_pdf", "canvas_clear", "ingest_begin"):
        assert gated not in names


async def test_core_includes_the_ninety_percent_path():
    expected = {
        "ingest_pdf", "list_documents", "get_document_index", "get_gold_regions",
        "get_page_text", "get_crop", "search_documents", "extract_pointed",
        "canvas_create_workspace", "canvas_get_state", "canvas_add_node",
        "canvas_update_node", "canvas_add_edge", "canvas_snapshot",
        "anchor_list_capabilities",
    }
    assert expected.issubset(tiering.CORE_NAMES)


# -- gated reachability ------------------------------------------------------ #
async def test_gated_tool_not_advertised_but_dispatches(tmp_path):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "pumps")
    server, _ = _multiproject_server()
    names = await _advertised(server)
    assert "get_pdf" not in names  # gated
    # ...yet a call routes correctly (missing slug -> error, NOT 'unknown tool').
    out = json.loads(await _call(server, "get_pdf", project="pumps", slug="ghost"))
    assert "error" in out
    assert "unknown" not in out["error"].lower()


async def test_capabilities_meta_lists_the_gated_set(tmp_path):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "pumps")
    server, _ = _multiproject_server()
    payload = json.loads(await _call(server, "anchor_list_capabilities", project="pumps"))
    caps = {g["capability"] for g in payload["capabilities"]}
    assert {"harness_ingest", "document_advanced", "canvas_advanced",
            "lifecycle_advanced", "cad", "sysml"}.issubset(caps)
    # Gated names appear in the catalog with descriptions.
    listed = {t["name"] for g in payload["capabilities"] for t in g["tools"]}
    for gated in ("ingest_begin", "get_pdf", "canvas_clear", "create_environment",
                  "inspect", "sysml_render"):
        assert gated in listed
    # No core tool leaks into the gated catalog.
    assert not (listed & tiering.CORE_NAMES)


async def test_capabilities_meta_works_without_project(tmp_path):
    create_env("local")
    server, _ = _multiproject_server()
    payload = json.loads(await _call(server, "anchor_list_capabilities"))
    assert payload["capabilities"]


# -- remove / rename lifecycle dispatch (#173) ------------------------------- #
async def test_remove_project_tool_dispatches(tmp_path):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "day1")
    server, _ = _multiproject_server()
    out = json.loads(await _call(server, "remove_project", {"name": "day1"}))
    assert out["removed"] == "day1"
    listing = json.loads(await _call(server, "list_projects"))
    assert "day1" not in [p["name"] for p in listing["projects"]]


async def test_remove_project_tool_refuses_nonempty(tmp_path):
    create_env("local")
    env = env_mod.resolve_environment("local")
    create_project(env, "pumps")
    (env.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")
    server, _ = _multiproject_server()
    out = json.loads(await _call(server, "remove_project", {"name": "pumps"}))
    assert out["error"] == "project_not_empty"
    assert out["documents"] == 1
    # force=True removes it
    forced = json.loads(
        await _call(
            server,
            "remove_project",
            {"name": "pumps", "force": True, "delete_data": True},
        )
    )
    assert forced["removed"] == "pumps"


async def test_rename_project_tool_dispatches(tmp_path):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "day1")
    server, _ = _multiproject_server()
    out = json.loads(await _call(server, "rename_project", old="day1", new="agentic"))
    assert out["renamed"] == "day1" and out["to"] == "agentic"
    listing = json.loads(await _call(server, "list_projects"))
    names = [p["name"] for p in listing["projects"]]
    assert "agentic" in names and "day1" not in names


async def test_rename_project_tool_rejects_existing(tmp_path):
    create_env("local")
    env = env_mod.resolve_environment("local")
    create_project(env, "pumps")
    create_project(env, "paper")
    server, _ = _multiproject_server()
    out = json.loads(await _call(server, "rename_project", old="pumps", new="paper"))
    assert "error" in out
    assert "already exists" in out["error"]


# -- extension auto-activation ----------------------------------------------- #
async def test_extension_autoexposed_when_project_has_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_FMU_DEMO", "1")
    create_env("local")
    router = ProjectRouter(env_arg="local")
    create_project(router.environment(), "pumps")
    server = build_mcp_server(router=router)

    # No FMU data: fmu tools gated out, capability listed as inactive.
    before = await _advertised(server)
    assert "fmu_inspect" not in before
    payload = json.loads(await _call(server, "anchor_list_capabilities", project="pumps"))
    fmu = next(g for g in payload["capabilities"] if g["capability"] == "fmu")
    assert fmu["active"] is False

    # Add an FMU model + make pumps the session default; fmu tools auto-appear.
    bundle = router.bundle_for("pumps")
    await bundle.fmu.upload_and_inspect(b"dummy-fmu", "pump.fmu")
    router.open_project("pumps")
    after = await _advertised(server)
    assert "fmu_inspect" in after
    assert "fmu_simulate" in after
    assert len(after) > len(before)


async def test_single_project_autoexposes_fmu_with_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_FMU_DEMO", "1")
    server, bundle = _single_project_server(tmp_path)
    assert "fmu_inspect" not in await _advertised(server)
    await bundle.fmu.upload_and_inspect(b"dummy-fmu", "pump.fmu")
    names = await _advertised(server)
    assert "fmu_inspect" in names
