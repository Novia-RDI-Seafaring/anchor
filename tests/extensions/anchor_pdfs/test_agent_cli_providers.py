"""The ``claude`` and ``codex`` providers run the vision stages through the user's own CLI.

A stand-in CLI on PATH records how it was called and answers like the real
one, so these tests pin the contract without a real CLI or a sign-in:

- the page image and the answer schema reach the CLI;
- no API key reaches the child process, so the CLI answers on its sign-in;
- the CLI's own MCP servers, settings and session history stay out;
- a missing, failing or signed-out CLI is a named error with the fix in it.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from anchor.extensions.anchor_pdfs.infra.llm import agent_cli
from anchor.extensions.anchor_pdfs.infra.llm.agent_cli import (
    REGIONS_SCHEMA,
    AgentCliError,
    AgentCliPageMdPolisher,
    AgentCliRegionExtractor,
    ClaudeCodeCli,
    CodexCli,
)

PNG = b"\x89PNG\r\n\x1a\nfake"
REGION = {
    "id": "r1", "kind": "table", "title": "Motor sizes", "description": "kW per frame",
    "member_item_ids": ["p2-i3"], "bbox": [10, 20, 300, 120], "tags": ["motor"], "entities": ["IEC80"],
}


def _fake_cli(tmp_path: Path, name: str, body: str) -> Path:
    """Write an executable stand-in for ``name`` that runs ``body`` (Python)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / name
    script.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return bin_dir


RECORD = """
import json, os, sys, pathlib
log = pathlib.Path(os.environ["FAKE_LOG"])
log.write_text(json.dumps({
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "files": sorted(os.listdir(".")),
    "keys": sorted(k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY") if k in os.environ),
    "schema": json.loads(pathlib.Path("schema.json").read_text()) if pathlib.Path("schema.json").exists() else None,
}))
"""

CLAUDE_OK = RECORD + """
answer = json.loads(os.environ["FAKE_ANSWER"])
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "structured_output": answer}))
"""

CODEX_OK = RECORD + """
answer = json.loads(os.environ["FAKE_ANSWER"])
out = sys.argv[sys.argv.index("--output-last-message") + 1]
pathlib.Path(out).write_text(json.dumps(answer))
"""


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")

    def use(name: str, body: str, answer: dict) -> Path:
        bin_dir = _fake_cli(tmp_path, name, body)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_ANSWER", json.dumps(answer))
        return tmp_path / "call.json"

    return use


@pytest.mark.asyncio
async def test_claude_regions_get_the_page_the_schema_and_no_api_key(fake_env):
    log = fake_env("claude", CLAUDE_OK, {"regions": [REGION]})

    regions = await AgentCliRegionExtractor(ClaudeCodeCli()).extract_page(
        page_image=PNG, page_no=2, docling_items=[{"id": "p2-i0"}], model="sonnet",
    )

    assert regions == [REGION]
    call = json.loads(log.read_text())
    argv = call["argv"]
    assert argv[0] == "-p" and "page.png" in argv[1] and "page 2" in argv[1]
    assert json.loads(argv[argv.index("--json-schema") + 1]) == REGIONS_SCHEMA
    assert argv[argv.index("--tools") + 1] == "Read"
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--bare" not in argv, "bare mode ignores the subscription sign-in"
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert "page.png" in call["files"]
    assert call["keys"] == []


@pytest.mark.asyncio
async def test_codex_regions_attach_the_image_and_read_the_last_message(fake_env):
    log = fake_env("codex", CODEX_OK, {"regions": [{**REGION, "bbox": None}]})

    regions = await AgentCliRegionExtractor(CodexCli()).extract_page(
        page_image=PNG, page_no=3, docling_items=[], model="default",
    )

    assert regions == [{k: v for k, v in REGION.items() if k != "bbox"}]
    call = json.loads(log.read_text())
    argv = call["argv"]
    assert "page 3" in argv[-1] and "member_item_ids" in argv[-1]
    assert argv[0] == "exec"
    assert Path(argv[argv.index("--image") + 1]).name == "page.png"
    assert Path(argv[argv.index("--output-schema") + 1]).name == "schema.json"
    assert call["schema"] == REGIONS_SCHEMA
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in argv and "--ignore-user-config" in argv
    assert "--model" not in argv, "'default' leaves the model to the CLI's own config"
    assert call["keys"] == []


@pytest.mark.asyncio
async def test_polisher_falls_back_to_the_seed_markdown_on_an_empty_answer(fake_env):
    fake_env("claude", CLAUDE_OK, {"markdown": "  "})

    md = await AgentCliPageMdPolisher(ClaudeCodeCli()).polish_page(
        page_image=PNG, page_no=1, deterministic_md="# Seed", docling_items=[], model="sonnet",
    )

    assert md == "# Seed"


def test_a_missing_cli_names_the_install_and_sign_in(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(AgentCliError, match="not on PATH.*codex login"):
        CodexCli().ask(prompt="x", image=PNG, schema={}, model="default")


def test_a_failing_cli_reports_its_exit_and_the_sign_in_fix(fake_env):
    fake_env("claude", "import sys\nprint('Invalid API key', file=sys.stderr)\nsys.exit(1)\n", {})
    with pytest.raises(AgentCliError, match="exited with code 1: Invalid API key.*claude"):
        ClaudeCodeCli().ask(prompt="x", image=PNG, schema={}, model="sonnet")


def test_an_unfinished_claude_run_is_an_error_not_empty_regions(fake_env):
    body = 'import json\nprint(json.dumps({"subtype": "error_max_structured_output_retries", "is_error": True}))\n'
    fake_env("claude", body, {})
    with pytest.raises(AgentCliError, match="error_max_structured_output_retries"):
        ClaudeCodeCli().ask(prompt="x", image=PNG, schema={}, model="sonnet")


@pytest.mark.parametrize(
    ("status", "ok", "says"),
    [
        ({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max",
          "email": "someone@example.com"}, True, "Claude plan (max)"),
        ({"loggedIn": True, "authMethod": "api_key"}, True, "may bill that account"),
        ({"loggedIn": False}, False, "not signed in"),
    ],
)
def test_claude_sign_in_status_never_shows_account_details(fake_env, status, ok, says):
    fake_env("claude", f"import json\nprint(json.dumps({status!r}))\n", {})
    signed_in, detail = ClaudeCodeCli().sign_in()
    assert signed_in is ok
    assert says in detail
    assert "example.com" not in detail


def test_egress_policy_routes_claude_and_codex_to_their_cli(monkeypatch):
    from anchor.infra.config import AnchorConfig
    from anchor.infra.egress_policy import EgressPolicyError, resolve_egress_policy

    for provider in ("claude", "codex"):
        cfg = AnchorConfig(provider=provider, embed_model="BAAI/bge-small-en-v1.5")
        policy = resolve_egress_policy(cfg)
        assert policy.agent_cli == provider
        assert policy.server_egress_allowed and not policy.remote_clients_enabled
        assert policy.api_key is None

    # A local-only environment never runs a cloud CLI.
    local = resolve_egress_policy(AnchorConfig(provider="claude", local_only=True,
                                               embed_model="BAAI/bge-small-en-v1.5"))
    assert local.agent_cli is None and not local.server_egress_allowed

    # No endpoint key to embed with: a remote embed model is refused.
    with pytest.raises(EgressPolicyError, match="requires an approved model credential"):
        resolve_egress_policy(AnchorConfig(provider="claude", embed_model="text-embedding-3-small"))


def test_runtime_builds_cli_backed_vision_stages(tmp_path):
    from anchor.adapters.project_runtime import build_ingest_service
    from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.config import AnchorConfig

    cfg = AnchorConfig(provider="codex", embed_model="BAAI/bge-small-en-v1.5", data_dir=tmp_path)
    service = build_ingest_service(cfg, MemoryEventBus(), MemoryDocStore(), embedder=object())

    assert isinstance(service.polisher, AgentCliPageMdPolisher)
    assert isinstance(service.region_extractor, AgentCliRegionExtractor)
    assert isinstance(service.region_extractor.cli, CodexCli)


def test_providers_are_offered_without_a_key():
    from anchor.infra.providers import get_provider

    for key in ("claude", "codex"):
        provider = get_provider(key)
        assert provider is not None and provider.does_vision and not provider.base_url_required
    assert agent_cli.AGENT_CLIS.keys() == {"claude", "codex"}


@pytest.mark.asyncio
async def test_an_empty_member_list_falls_back_to_the_bbox(fake_env):
    fake_env("claude", CLAUDE_OK, {"regions": [{**REGION, "member_item_ids": []}]})

    regions = await AgentCliRegionExtractor(ClaudeCodeCli()).extract_page(
        page_image=PNG, page_no=1, docling_items=[], model="sonnet",
        page_size=[595.0, 842.0], dpi=150,
    )

    assert "member_item_ids" not in regions[0]
    assert regions[0]["bbox"] == REGION["bbox"]
