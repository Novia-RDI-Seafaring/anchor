"""Vision stages run by the user's own agent CLI: Claude Code or Codex.

The ``claude`` and ``codex`` providers need no API key. Each page goes to the
CLI the user already installed and signed in to (``claude`` with a Claude
plan, ``codex`` with a ChatGPT plan), run once per page in a scratch
directory with the page PNG beside it and a JSON schema for the answer.

Anchor never reads, stores or forwards the CLI's credentials. It runs the
unmodified binary as a subprocess, and the child gets no ``ANTHROPIC_API_KEY``
/ ``OPENAI_API_KEY``, so the CLI answers on the user's own sign-in rather
than billing an API key that happens to be in the environment.

Each call is isolated from the user's own CLI setup: no MCP servers (an
Anchor MCP server there would start Anchor again), no hooks or skills, no
session history, and read-only access to the scratch directory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .prompts import polish_prompt, region_prompt

logger = logging.getLogger(__name__)

#: One page, one answer. Generous: a dense table page can take a minute.
CALL_TIMEOUT_S = 300.0

#: Model value that means "whatever the CLI is configured to use".
CLI_DEFAULT_MODEL = "default"

_KINDS = ["chart", "spec_block", "table", "figure", "diagram", "text"]

#: Strict schema (every property required, no extras) so both CLIs accept
#: it: Codex's structured output rejects optional properties.
REGIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["regions"],
    "properties": {
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "kind", "title", "description", "member_item_ids", "bbox", "tags", "entities",
                ],
                "properties": {
                    "id": {"type": "string"},
                    # Preferred geometry: the Docling items the region covers.
                    "member_item_ids": {"type": "array", "items": {"type": "string"}},
                    "kind": {"type": "string", "enum": _KINDS},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "bbox": {
                        "type": ["array", "null"],
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "entities": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

POLISH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["markdown"],
    "properties": {"markdown": {"type": "string"}},
}

_IMAGE_NOTE = (
    "The page image is the file {name} in the current directory; look at it "
    "before answering. Answer only with the requested JSON."
)


class AgentCliError(RuntimeError):
    """The agent CLI is missing, signed out, or did not answer as asked."""


def _child_env() -> dict[str, str]:
    """The parent's environment without API keys, so the CLI uses its sign-in."""
    drop = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY"}
    return {k: v for k, v in os.environ.items() if k not in drop}


class AgentCli:
    """One agent CLI that answers a prompt about one image with schema-shaped JSON."""

    name = "agent"
    binary = ""
    sign_in_hint = ""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or self.binary

    def resolve(self) -> str:
        path = shutil.which(self.executable)
        if not path:
            raise AgentCliError(
                f"provider {self.name!r} runs the `{self.executable}` CLI, which is not on PATH. "
                f"Install it and {self.sign_in_hint}."
            )
        return path

    def ask(self, *, prompt: str, image: bytes, schema: dict[str, Any], model: str) -> dict[str, Any]:
        executable = self.resolve()
        with tempfile.TemporaryDirectory(prefix="anchor-page-") as tmp:
            workdir = Path(tmp)
            (workdir / "page.png").write_bytes(image)
            (workdir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
            argv = self.argv(executable, workdir, prompt + "\n\n" + _IMAGE_NOTE.format(name="page.png"),
                             schema, model)
            try:
                done = subprocess.run(
                    argv, cwd=workdir, env=_child_env(), stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=CALL_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as exc:
                raise AgentCliError(f"`{self.binary}` did not answer within {CALL_TIMEOUT_S:.0f}s") from exc
            if done.returncode != 0:
                detail = (done.stderr or done.stdout or "").strip()[-600:]
                raise AgentCliError(
                    f"`{self.binary}` exited with code {done.returncode}: {detail}. "
                    f"If it is signed out, {self.sign_in_hint}."
                )
            return self.parse(done.stdout, workdir)

    def found(self) -> bool:
        return shutil.which(self.executable) is not None

    def sign_in(self) -> tuple[bool, str]:
        """Whether the CLI is signed in, and a one-line description with no account details."""
        try:
            done = subprocess.run(
                [self.resolve(), *self.status_argv], env=_child_env(), stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=30,
            )
        except (AgentCliError, OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        return self.read_status(done)

    status_argv: tuple[str, ...] = ()

    def read_status(self, done: subprocess.CompletedProcess[str]) -> tuple[bool, str]:
        raise NotImplementedError

    def argv(self, executable: str, workdir: Path, prompt: str, schema: dict[str, Any],
             model: str) -> list[str]:
        raise NotImplementedError

    def parse(self, stdout: str, workdir: Path) -> dict[str, Any]:
        raise NotImplementedError


class ClaudeCodeCli(AgentCli):
    """``claude -p`` with ``--json-schema``; the page is read with the Read tool."""

    name = "claude"
    binary = "claude"
    sign_in_hint = "sign in once with `claude` (then /login) using your Claude plan"
    status_argv = ("auth", "status", "--json")

    def read_status(self, done):
        try:
            status = json.loads(done.stdout)
        except json.JSONDecodeError:
            return False, "could not read `claude auth status`"
        if not status.get("loggedIn"):
            return False, "not signed in"
        method = status.get("authMethod") or "unknown"
        if method != "claude.ai":
            return True, f"signed in ({method}); calls may bill that account, not a Claude plan"
        plan = status.get("subscriptionType")
        return True, f"signed in with a Claude plan{f' ({plan})' if plan else ''}"

    def argv(self, executable, workdir, prompt, schema, model):
        argv = [
            executable, "-p", prompt,
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            # Only the Read tool, pre-approved, so the page can be opened and
            # nothing else can run. No MCP servers, settings files, skills or
            # session history from the user's own setup.
            "--tools", "Read", "--allowedTools", "Read",
            "--strict-mcp-config", "--setting-sources", "",
            "--disable-slash-commands", "--no-session-persistence",
        ]
        if model and model != CLI_DEFAULT_MODEL:
            argv += ["--model", model]
        return argv

    def parse(self, stdout, workdir):
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise AgentCliError(f"`claude` returned non-JSON output: {stdout[:200]!r}") from exc
        if result.get("is_error") or result.get("subtype") != "success":
            raise AgentCliError(
                f"`claude` did not finish the page: {result.get('subtype')}: "
                f"{str(result.get('result'))[:300]}"
            )
        answer = result.get("structured_output")
        if not isinstance(answer, dict):
            raise AgentCliError("`claude` finished without structured output")
        return answer


class CodexCli(AgentCli):
    """``codex exec`` with ``--image`` and ``--output-schema``, read-only sandbox."""

    name = "codex"
    binary = "codex"
    sign_in_hint = "sign in once with `codex login` using your ChatGPT plan"
    status_argv = ("login", "status")

    def read_status(self, done):
        line = ((done.stdout or "") + (done.stderr or "")).strip().splitlines()
        first = line[0] if line else ""
        if done.returncode != 0 or "not logged in" in first.lower():
            return False, "not signed in"
        if "api key" in first.lower():
            return True, "signed in with an API key; calls bill that key, not a ChatGPT plan"
        return True, first or "signed in"

    def argv(self, executable, workdir, prompt, schema, model):
        argv = [
            executable, "exec",
            "--image", str(workdir / "page.png"),
            "--output-schema", str(workdir / "schema.json"),
            "--output-last-message", str(workdir / "answer.json"),
            "--sandbox", "read-only",
            "--skip-git-repo-check", "--ephemeral",
            # The user's config.toml may add MCP servers or tools; sign-in
            # still comes from CODEX_HOME.
            "--ignore-user-config",
            "--cd", str(workdir),
        ]
        if model and model != CLI_DEFAULT_MODEL:
            argv += ["--model", model]
        return argv + [prompt]

    def parse(self, stdout, workdir):
        answer_file = workdir / "answer.json"
        if not answer_file.is_file():
            raise AgentCliError("`codex` finished without writing an answer")
        text = answer_file.read_text(encoding="utf-8").strip()
        try:
            answer = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentCliError(f"`codex` answered with non-JSON text: {text[:200]!r}") from exc
        if not isinstance(answer, dict):
            raise AgentCliError("`codex` answer is not a JSON object")
        return answer


AGENT_CLIS: dict[str, type[AgentCli]] = {"claude": ClaudeCodeCli, "codex": CodexCli}


def agent_cli_for(provider: str) -> AgentCli:
    return AGENT_CLIS[provider]()


class AgentCliRegionExtractor:
    """``RegionExtractor`` port over an agent CLI."""

    def __init__(self, cli: AgentCli) -> None:
        self.cli = cli

    async def extract_page(self, *, page_image: bytes, page_no: int,
                           docling_items: list[dict[str, Any]], model: str,
                           page_size: list[float] | None = None,
                           dpi: int | None = None) -> list[dict[str, Any]]:
        prompt = region_prompt(page_no, docling_items, page_size=page_size, dpi=dpi)
        answer = await asyncio.to_thread(
            self.cli.ask, prompt=prompt, image=page_image, schema=REGIONS_SCHEMA, model=model,
        )
        regions = []
        for region in answer.get("regions") or []:
            if not isinstance(region, dict):
                continue
            # The strict schema makes every field present; an empty geometry
            # field means "not given", so drop it and let the other one count.
            if region.get("bbox") is None:
                region = {k: v for k, v in region.items() if k != "bbox"}
            if not region.get("member_item_ids"):
                region = {k: v for k, v in region.items() if k != "member_item_ids"}
            regions.append(region)
        return regions


class AgentCliPageMdPolisher:
    """``PageMdPolisher`` port over an agent CLI."""

    def __init__(self, cli: AgentCli) -> None:
        self.cli = cli

    async def polish_page(self, *, page_image: bytes, page_no: int, deterministic_md: str,
                          docling_items: list[dict[str, Any]], model: str) -> str:
        answer = await asyncio.to_thread(
            self.cli.ask, prompt=polish_prompt(page_no, deterministic_md, docling_items),
            image=page_image, schema=POLISH_SCHEMA, model=model,
        )
        markdown = answer.get("markdown")
        return markdown if isinstance(markdown, str) and markdown.strip() else deterministic_md
