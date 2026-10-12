"""A remote embed model without a visible key degrades, it does not brick.

Claude Desktop starts ``anchor-mcp --env <env>`` without the user's shell
variables. Read-only operations must still work on every adapter; only calls
that reach the remote model fail, with a structured error naming the
environment's ``.env`` file.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolRequest, CallToolRequestParams
from typer.testing import CliRunner

from anchor.adapters.cli import check as check_mod
from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.infra import environment as env_mod
from anchor.infra.egress_policy import EgressPolicyError, resolve_egress_policy
from anchor.infra.environment import create_env, ensure_project, resolve_project

runner = CliRunner()
ENV = "keyed"
SECRET = "sk-test-never-print-me"


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in (
        "ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR",
        "ANCHOR_OPENAI_API_KEY", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: (True, None))


def _openai_env():
    env = create_env(
        ENV, settings={"provider": "openai", "embed_model": "text-embedding-3-small"}
    )
    return env, env.root / ".env"


async def _call(server, name: str, **arguments) -> dict:
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(req)
    return json.loads(result.root.content[0].text)


def _assert_missing_key_error(body: dict, dotenv) -> None:
    assert body["error"] == "missing_model_credential"
    assert str(dotenv) in body["hint"]
    assert "ANCHOR_OPENAI_API_KEY" in body["hint"]
    assert "Claude Desktop" in body["hint"]


# -- MCP --------------------------------------------------------------------- #
async def test_mcp_reads_work_and_search_explains_missing_key():
    _, dotenv = _openai_env()
    server = build_mcp_server(router=ProjectRouter(env_arg=ENV))

    status = await _call(server, "anchor_status")
    cred = status["credential"]
    assert cred["required"] is True
    assert cred["present"] is False
    assert cred["source"] is None
    assert cred["env_file"] == str(dotenv)
    assert "Claude Desktop" in cred["hint"]

    assert await _call(server, "list_documents") == []

    _assert_missing_key_error(await _call(server, "search_documents", query="pump"), dotenv)


# -- CLI --------------------------------------------------------------------- #
def test_cli_list_works_and_search_explains_missing_key():
    env, dotenv = _openai_env()
    data_dir = str(ensure_project(env, "default"))
    listed = runner.invoke(cli_app, ["list", "--data-dir", data_dir])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout) == []

    searched = runner.invoke(cli_app, ["search", "pump", "--data-dir", data_dir])
    assert searched.exit_code == 1
    _assert_missing_key_error(json.loads(searched.stderr.strip().splitlines()[-1]), dotenv)


def test_check_reports_missing_key_with_desktop_hint():
    _openai_env()
    result = runner.invoke(cli_app, ["check", "--env", ENV])
    assert "NOT set" in result.output
    assert "Claude Desktop" in result.output


def test_check_reports_process_only_key_is_invisible_to_apps():
    _, dotenv = _openai_env()
    result = runner.invoke(
        cli_app, ["check", "--env", ENV], env={"ANCHOR_OPENAI_API_KEY": SECRET}
    )
    assert "from process environment" in result.output
    assert "will not see it" in result.output
    assert str(dotenv) in result.output
    assert SECRET not in result.output


def test_check_reports_env_file_key_source():
    _, dotenv = _openai_env()
    dotenv.write_text(f"ANCHOR_OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
    result = runner.invoke(cli_app, ["check", "--env", ENV])
    assert "from environment .env file" in result.output
    assert "will not see it" not in result.output
    assert SECRET not in result.output


# -- HTTP -------------------------------------------------------------------- #
def test_http_status_and_list_work_and_search_explains_missing_key():
    _, dotenv = _openai_env()
    config = resolve_project(ENV, "default").config
    runtime = build_project_runtime(config, profile=RuntimeProfile.INGEST)
    client = TestClient(build_app(runtime))

    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["credential"]["present"] is False

    assert client.get("/api/documents").status_code == 200

    searched = client.get("/api/documents/_search", params={"q": "pump"})
    assert searched.status_code == 503
    _assert_missing_key_error(searched.json(), dotenv)


def test_http_status_reports_env_file_source_without_the_key():
    _, dotenv = _openai_env()
    dotenv.write_text(f"ANCHOR_OPENAI_API_KEY={SECRET}\n", encoding="utf-8")
    config = resolve_project(ENV, "default").config
    runtime = build_project_runtime(config, profile=RuntimeProfile.INGEST)
    body = TestClient(build_app(runtime)).get("/api/status").json()
    assert body["credential"]["present"] is True
    assert body["credential"]["source"] == "env_file"
    assert SECRET not in json.dumps(body)


# -- policy semantics stay intact -------------------------------------------- #
@pytest.mark.parametrize("provider", ["local", "harness"])
def test_no_egress_provider_still_rejects_remote_embed_model(provider):
    create_env("noegress", settings={"provider": provider, "embed_model": "BAAI/bge-small-en-v1.5"})
    config = resolve_project("noegress", "default").config.model_copy(
        update={"embed_model": "text-embedding-3-small"}
    )
    with pytest.raises(EgressPolicyError):
        build_project_runtime(config, profile=RuntimeProfile.CANVAS)


def test_operations_needing_the_model_still_require_the_credential():
    _openai_env()
    config = resolve_project(ENV, "default").config
    with pytest.raises(EgressPolicyError):
        resolve_egress_policy(config)
