# Agent configuration

ANCHOR exposes local tools through the `anchor-mcp` stdio executable. The
connected agent decides when to call those tools based on the user's request,
the MCP tool descriptions, and any project instructions supplied to the agent.

ANCHOR is not an autonomous decision-maker. It provides document, canvas, CAD,
SysML, and optional FMU operations that an MCP-capable agent can call when the
task needs project data.

## Before connecting an agent

Install ANCHOR and configure a project:

```bash
uv tool install anchor-kb
cd ~/my-project
anchor init        # pick provider / data zone; writes anchor.toml
anchor serve
```

`anchor-mcp` can run as a local stdio process without exposing a network MCP
endpoint. Keep `anchor serve` running when you want the browser UI, live canvas
updates, or canvas snapshots.

## Project resolution (no baked data dir)

Register `anchor-mcp` **without** a `--data-dir`. The server resolves the active
project from `anchor.toml`, discovered by walking up from the directory the
agent launches it in. So one registration works for every `anchor init` project:
open the agent in a project folder and the tools target that project.

The effective data dir still follows ANCHOR's normal precedence: explicit args,
`ANCHOR_*` environment variables or `.env`, project `anchor.toml`, then
`~/anchor-data`.

To name a project explicitly, when the server's working directory is not the
project, add `--project <folder>` to the args. The examples below use the
folder-resolving form.

## Confirm the resolved project

If an agent can see ANCHOR tools but reports no documents or canvases, ask it to
call:

```text
anchor_status
```

The result shows the MCP server's working directory, resolved `anchor.toml`,
data directory, and current document and canvas counts. Compare those paths
with the project you expected. If they point somewhere else, restart the client
from the project folder or add `--project <folder>` to the `anchor-mcp` args.

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

If ANCHOR appears empty, call `anchor_status` and compare the resolved data
directory with the project folder before assuming there is no data.
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
  anchor-mcp --base-url http://localhost:8002
claude mcp list
```

Restart Claude Code after registration. Within a Claude Code session, run:

```text
/mcp
```

The `anchor` server should appear with its available tools. Put the optional
project instruction in `CLAUDE.md` when a repository needs it.

Claude Desktop is a different client. `anchor install claude-code` does not
write Claude Desktop's `claude_desktop_config.json`. For Claude Desktop, add an
`mcpServers.anchor` entry that runs `anchor-mcp` as a local stdio command, then
restart Claude Desktop. If the client reports a tool-name validation error, use
an ANCHOR version whose MCP tools use underscore names such as `sysml_render`
and `fmu_simulate`.

## Codex

Codex CLI and the Codex IDE extension share the same MCP configuration. Add
ANCHOR with:

```bash
codex mcp add anchor -- \
  anchor-mcp --base-url http://localhost:8002
codex mcp list
```

Alternatively, add this to `~/.codex/config.toml`:

```toml
[mcp_servers.anchor]
command = "anchor-mcp"
args = ["--base-url", "http://localhost:8002"]
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
  --base-url http://localhost:8002
gemini mcp list
```

On Windows PowerShell:

```powershell
gemini mcp add --scope user anchor anchor-mcp -- --base-url http://localhost:8002
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

## Generic stdio client

For another MCP client that accepts `mcpServers` JSON:

```json
{
  "mcpServers": {
    "anchor": {
      "command": "anchor-mcp",
      "args": [
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
