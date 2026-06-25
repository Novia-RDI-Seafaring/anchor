# Agent configuration

ANCHOR exposes local tools through the `anchor-mcp` stdio executable. The
connected agent decides when to call those tools based on the user's request,
the MCP tool descriptions, and any project instructions supplied to the agent.

ANCHOR is not an autonomous decision-maker. It provides document, canvas, CAD,
SysML, and optional FMU operations that an MCP-capable agent can call when the
task needs project data.

## Before connecting an agent

Install ANCHOR and create an environment:

```bash
uv tool install anchor-kb
anchor env create local  # pick provider / data zone (name it whatever you like)
anchor serve
```

`anchor-mcp` can run as a local stdio process without exposing a network MCP
endpoint. Keep `anchor serve` running when you want the browser UI, live canvas
updates, or canvas snapshots.

## Environment selection

One MCP server serves one **environment**, named with `--env`:

```bash
anchor-mcp --env local
```

Projects inside that environment are addressed by a per-call `project` argument;
omit it for the default project. `list_projects` enumerates them. A second
environment is a second named server. The installers
(`anchor install claude-desktop --env <name>`) write the entry for you. The
examples below show the manual form; add `--env <name>` to select a
non-default environment.

## Confirm the resolved project

If an agent can see ANCHOR tools but reports no documents or canvases, ask it to
call `anchor_status` (the resolved environment and the active project's data
directory and counts) and `list_projects`. If it is on the wrong project, pass
the right `project` argument. To use a different environment, add a second named
server.

## Optional project instruction

MCP clients expose ANCHOR's tool names and schemas to the model. A short project
instruction can make tool selection more consistent:

```text
When a task involves ANCHOR canvases, ingested documents, source evidence,
PDFs, CAD, SysML, FMU, or project artifacts, prefer ANCHOR MCP tools over
guessing from memory.

For document questions, retrieve source regions first and include a source
reference when available.

For canvas questions, inspect the workspace state before editing it. Preserve
existing nodes and edges unless the user asks to remove them.

If ANCHOR appears empty, call `anchor_status` and `list_projects`, and pass the
right `project` argument before assuming there is no data.
```

Keep this instruction short. It should guide tool selection without attempting
to encode every possible workflow.

## Claude Code

The simplest path is the bundled installer, which writes the MCP entry **and**
the ANCHOR skill:

```bash
anchor install claude-code
```

Or register the server manually with the CLI:

```bash
claude mcp add --transport stdio --scope user anchor -- \
  anchor-mcp --env local --base-url http://localhost:8002
claude mcp list
```

Restart Claude Code after registration. Within a Claude Code session, run:

```text
/mcp
```

The `anchor` server should appear with its available tools. Put the optional
project instruction in `CLAUDE.md` when a repository needs it.

Claude Desktop is a different client with its own installer:

```bash
anchor install claude-desktop --env local
```

It writes a named pointer entry into `claude_desktop_config.json`, echoes the
egress zone, and supports `--name` for a second environment. If a client
reports a tool-name validation error, use an ANCHOR version whose MCP tools use
underscore names such as `sysml_render` and `fmu_simulate`.

## Codex

Codex CLI and the Codex IDE extension share the same MCP configuration. Add
ANCHOR with:

```bash
codex mcp add anchor -- \
  anchor-mcp --env local --base-url http://localhost:8002
codex mcp list
```

Alternatively, add this to `~/.codex/config.toml`:

```toml
[mcp_servers.anchor]
command = "anchor-mcp"
args = ["--env", "local", "--base-url", "http://localhost:8002"]
```

A trusted project can use `.codex/config.toml` instead. Put the optional
project instruction in `AGENTS.md`.

## OpenCode

OpenCode reads global configuration from `~/.config/opencode/opencode.json`.
A repository can also provide a project-specific `opencode.json`.

Add:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "anchor": {
      "type": "local",
      "command": [
        "anchor-mcp",
        "--env",
        "local",
        "--base-url",
        "http://localhost:8002"
      ],
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

If an `opencode.json` file already exists, merge only the `mcp.anchor` entry
into it. Verify the connection with:

```bash
opencode mcp list
```

## Gemini CLI

Gemini CLI can register ANCHOR as a local stdio MCP server:

```bash
gemini mcp add --scope user anchor anchor-mcp -- \
  --env local --base-url http://localhost:8002
gemini mcp list
```

On Windows PowerShell:

```powershell
gemini mcp add --scope user anchor anchor-mcp -- --env local --base-url http://localhost:8002
gemini mcp list
```

Alternatively, add ANCHOR manually to `~/.gemini/settings.json` on Linux or
macOS, or `%USERPROFILE%\.gemini\settings.json` on Windows:

```json
{
  "mcpServers": {
    "anchor": {
      "command": "anchor-mcp",
      "args": [
        "--env",
        "local",
        "--base-url",
        "http://localhost:8002"
      ],
      "timeout": 600000
    }
  }
}
```

If the file already exists, merge only the `mcpServers.anchor` entry. Gemini
CLI also supports project-local `.gemini/settings.json` files when the MCP
server should apply only to one project.

## Cursor

ANCHOR provides a Cursor helper:

```bash
anchor install cursor
```

Restart Cursor after registration and confirm that the `anchor` MCP server is
enabled.

Cursor has no global skills directory, so the MCP entry gives the agent tools
but not the project conventions. When a Cursor workspace is an Anchor project,
run the helper from that folder with `--rules` to also write a project-scoped
`.cursor/rules/anchor.mdc` that points the agent at `AGENTS.md` plus the
CLI/MCP surfaces:

```bash
cd ~/work/pumps
anchor install cursor --rules
```

The rules file is a short pointer, not a copy of `AGENTS.md`. The write is
idempotent and keeps any edits you make unless you pass `--force`.

## Generic stdio client

For another MCP client that accepts `mcpServers` JSON:

```json
{
  "mcpServers": {
    "anchor": {
      "command": "anchor-mcp",
      "args": [
        "--env",
        "local",
        "--base-url",
        "http://localhost:8002"
      ]
    }
  }
}
```

## Executable path troubleshooting

If a client cannot find `anchor-mcp`, locate the installed executable:

=== "Windows PowerShell"

    ```powershell
    Get-Command anchor-mcp
    ```

=== "Linux or macOS"

    ```bash
    command -v anchor-mcp
    ```

Replace `"anchor-mcp"` with the returned absolute path in the relevant client
configuration.

## Client references

- [Claude Code MCP setup](https://code.claude.com/docs/en/mcp)
- [Codex MCP setup](https://developers.openai.com/codex/mcp)
- [Gemini CLI MCP servers](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html)
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode configuration](https://opencode.ai/docs/config/)
