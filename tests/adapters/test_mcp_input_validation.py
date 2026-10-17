"""Tool schemas guard every protocol call before project or thread mutations."""
from __future__ import annotations

import json

import pytest
from mcp.client import Client

from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.infra import environment as env_mod
from anchor.infra.activity import ActivityLog

RENAME = [{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "After"}}}]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / "registry")
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANCHOR_FMU_DEMO", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    env_mod.create_env("validation", settings={"provider": "local", "local_only": True})
    router = ProjectRouter(env_arg="validation")
    return router, router.bundle_for(None)


async def _thread(runtime):
    await runtime.workspace.create_workspace("cv")
    await runtime.workspace.add_node("cv", id="n1", label="Before", x=0, y=0)
    return await runtime.intents.enqueue(
        "user_request", origin_canvas_id="cv", payload={"text": "Rename"},
        targets=[{"workspace_id": "cv", "node_id": "n1"}],
    )


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("flag", ["apply", "resolve"])
@pytest.mark.parametrize("invalid", ["false", 0, None])
async def test_invalid_intent_flags_do_not_change_canvas_thread_or_activity(project, mode, flag, invalid):
    router, runtime = project
    intent = await _thread(runtime)
    before_state = await runtime.workspace.get_state("cv")
    before_events = await runtime.workspace.store.read_events("cv")
    before_thread = intent.to_dict()
    activity = ActivityLog(runtime.config.data_dir)
    before_activity = activity.read()
    async with Client(build_mcp_server(router=router), mode=mode) as client:
        result = await client.call_tool("intent_act", {
            "id": intent.id, "text": "Rename", "ops": RENAME,
            "apply": False, "resolve": False, flag: invalid,
        })
        assert result.is_error
        assert result.content[0].text.startswith("Input validation error:")
        assert "boolean" in result.content[0].text
    assert await runtime.workspace.get_state("cv") == before_state
    assert await runtime.workspace.store.read_events("cv") == before_events
    assert (await runtime.intents.get(intent.id)).to_dict() == before_thread
    assert activity.read() == before_activity


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("flags,applied,resolved", [
    ({}, True, False),
    ({"apply": False, "resolve": False}, False, False),
    ({"apply": True, "resolve": False}, True, False),
    ({"apply": True, "resolve": True}, True, True),
])
async def test_valid_intent_flags_keep_staging_applying_resolving_and_logging(
    project, mode, flags, applied, resolved,
):
    router, runtime = project
    intent = await _thread(runtime)
    async with Client(build_mcp_server(router=router), mode=mode) as client:
        result = await client.call_tool("intent_act", {
            "project": "default", "id": intent.id, "text": "Rename", "ops": RENAME, **flags,
        })
        assert not result.is_error
        assert bool(json.loads(result.content[0].text)["applied"]) is applied
    state = await runtime.workspace.get_state("cv")
    assert state["nodes"][0]["label"] == ("After" if applied else "Before")
    thread = await runtime.intents.get(intent.id)
    assert thread.status == ("resolved" if resolved else "pending")
    assert len(thread.items) == 1
    assert thread.items[0].state == ("applied" if applied else "pending")
    calls = ActivityLog(runtime.config.data_dir).read()
    assert len(calls) == 1
    assert calls[0]["kind"] == "mcp" and calls[0]["name"] == "intent_act"
    assert calls[0]["intent"] == intent.id


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("tool,arguments", [
    ("remove_project", {"name": "default", "delete_data": "false"}),
    ("sysml_render", {"workspace_slug": "cv", "text": 42}),
    ("sysml.render", {"workspace_slug": "cv", "text": 42}),
    ("fmu_simulate", {"slug": "missing", "stop_time": "1.0"}),
    ("fmu.simulate", {"slug": "missing", "stop_time": "1.0"}),
])
async def test_unadvertised_tools_and_legacy_aliases_are_validated(project, mode, tool, arguments):
    router, runtime = project
    await _thread(runtime)
    before = await runtime.workspace.get_state("cv")
    async with Client(build_mcp_server(router=router), mode=mode) as client:
        listing = await client.list_tools()
        assert tool not in {item.name for item in listing.tools}
        result = await client.call_tool(tool, arguments)
        assert result.is_error
        assert result.content[0].text.startswith("Input validation error:")
    assert router.bundle_for(None) is runtime
    assert await runtime.workspace.get_state("cv") == before
    assert ActivityLog(runtime.config.data_dir).read() == []


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_validation_precedes_project_resolution_and_keeps_execution_error_payloads(project, mode):
    router, runtime = project
    async with Client(build_mcp_server(router=router), mode=mode) as client:
        invalid = await client.call_tool("intent_act", {
            "project": "missing", "id": "missing", "text": "Rename", "ops": RENAME,
            "apply": "false",
        })
        assert invalid.is_error
        assert invalid.content[0].text.startswith("Input validation error:")
        missing = await client.call_tool("intent_act", {
            "project": "missing", "id": "missing", "text": "Rename", "ops": RENAME,
            "apply": False,
        })
        assert not missing.is_error
        assert json.loads(missing.content[0].text)["error"] == "no_project"
        unknown = await client.call_tool("unknown_tool", {})
        assert not unknown.is_error
        assert "unknown tool" in json.loads(unknown.content[0].text)["error"]
