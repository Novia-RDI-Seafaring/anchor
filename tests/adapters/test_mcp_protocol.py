"""Public SDK clients exercise discovery, dispatch and both protocol eras."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError
from mcp.types import Implementation

from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.infra import environment as env_mod
from anchor.infra.config import AnchorConfig
from tests.extensions.anchor_pdfs.test_crop_inline_image import PNG


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_discovery_dispatch_images_and_client_attribution(tmp_path, mode):
    runtime = build_project_runtime(
        AnchorConfig(data_dir=tmp_path, provider="local", local_only=True, _env_file=None),
        profile=RuntimeProfile.INGEST,
    )
    await runtime.workspace.create_workspace("protocol")
    await runtime.doc_store.write_crop("doc", "1/r1.png", PNG)
    server = build_mcp_server(bundle=runtime)
    async with Client(server, mode=mode, client_info=Implementation(
        name="migration-test", version="1",
    )) as client:
        assert client.protocol_version == ("2026-07-28" if mode == "auto" else "2025-11-25")
        resources = await client.list_resources()
        assert resources.resources[0].uri == "anchor://help"
        help_text = await client.read_resource("anchor://help")
        assert help_text.contents[0].mime_type == "text/markdown"
        assert "Anchor" in help_text.contents[0].text
        with pytest.raises(MCPError):
            await client.read_resource("anchor://missing")
        tools = await client.list_tools()
        assert any(t.name == "canvas_add_node" and t.input_schema for t in tools.tools)
        result = await client.call_tool("canvas_add_node", {
            "workspace_slug": "protocol", "id": "one", "label": "One",
        })
        event = json.loads(result.content[0].text)["event"]
        assert event["actor"]["label"] == "migration-test"
        assert not result.is_error
        missing = await client.call_tool("unknown_tool", {})
        assert "error" in json.loads(missing.content[0].text)

        image = await client.call_tool("get_crop", {"slug": "doc", "rel_path": "1/r1.png"})
        assert image.content[0].type == "image"
        assert image.content[0].mime_type == "image/png"
        assert base64.b64decode(image.content[0].data) == PNG


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_project_lifecycle_routing_and_tiering_in_one_connection(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / "registry")
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    env_mod.create_env("migration", settings={"provider": "local", "local_only": True})
    router = ProjectRouter(env_arg="migration")
    async with Client(build_mcp_server(router=router), mode=mode) as client:
        async def call(tool_name, **arguments):
            result = await client.call_tool(tool_name, arguments)
            assert not result.is_error
            return json.loads(result.content[0].text)

        for project in ("alpha", "beta"):
            assert (await call("create_project", name=project))["created"] == project
        assert (await call("open_project", name="alpha"))["session_default"] == "alpha"
        await call("canvas_create_workspace", slug="board")
        before = await client.list_tools(cache_mode="refresh")
        assert "sysml_render" not in {tool.name for tool in before.tools}
        await call("canvas_add_node", workspace_slug="board", id="model", node_type="sysml:block",
                   label="Model", x=0, y=0)
        active = await client.list_tools(cache_mode="refresh")
        assert "sysml_render" in {tool.name for tool in active.tools}
        await call("open_project", name="beta")
        assert await call("canvas_list_workspaces") == []
        alpha = await call("canvas_list_workspaces", project="alpha")
        assert [workspace["slug"] for workspace in alpha] == ["board"]
        after = await client.list_tools(cache_mode="refresh")
        assert "sysml_render" not in {tool.name for tool in after.tools}
        missing = await call("canvas_list_workspaces", project="missing")
        assert missing["error"] == "no_project"
        assert {"alpha", "beta"}.issubset(missing["available"])
        assert (await call("rename_project", old="alpha", new="renamed"))["renamed"] == "alpha"
        assert (await call("remove_project", name="beta"))["removed"] == "beta"


def _stdio_parameters(tmp_path, binding="data-dir"):
    config = tmp_path / "anchor.toml"
    config.write_text('[anchor]\nprovider = "local"\nlocal_only = true\n', encoding="utf-8")
    env = {name: value for name, value in os.environ.items()
           if not name.startswith("ANCHOR_") and name != "OPENAI_API_KEY"}
    env.update(ANCHOR_CONFIG=str(config), ANCHOR_PROVIDER="local", ANCHOR_LOCAL_ONLY="true",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    executable = Path(sys.executable).with_name("anchor-mcp.exe" if os.name == "nt" else "anchor-mcp")
    assert executable.is_file(), "Install Anchor before running its entrypoint smoke test"
    # A missing named environment proves --env startup without touching the
    # user's registry; project operations must return the usual remedy.
    arguments = (["--data-dir", str(tmp_path / "data")] if binding == "data-dir"
                 else ["--env", "mcp-v2-smoke-" + tmp_path.name.lower().replace("_", "-")])
    return StdioServerParameters(
        command=str(executable), args=arguments,
        cwd=str(tmp_path), env=env,
    )


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("binding", ["data-dir", "env"])
async def test_stdio_subprocess_discovers_resources(tmp_path, mode, binding):
    async with Client(_stdio_parameters(tmp_path, binding), mode=mode, read_timeout_seconds=20) as client:
        resources = await client.list_resources()
        assert [r.uri for r in resources.resources] == ["anchor://help"]
        content = await client.read_resource("anchor://help")
        assert content.contents[0].text
        tools = await client.list_tools()
        assert "anchor_status" in {t.name for t in tools.tools}
        status = await client.call_tool("anchor_status", {})
        payload = json.loads(status.content[0].text)
        if binding == "data-dir":
            assert Path(payload["data_dir"]["path"]) == tmp_path / "data"
        else:
            assert payload["error"] == "no_environment"


def test_stdio_subprocess_exits_on_stdin_eof(tmp_path):
    params = _stdio_parameters(tmp_path)
    process = subprocess.Popen(
        [params.command, *params.args], cwd=params.cwd, env=params.env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(input=b"", timeout=20)
        assert process.returncode == 0, stderr.decode(errors="replace")
        assert stdout == b""
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=10)
