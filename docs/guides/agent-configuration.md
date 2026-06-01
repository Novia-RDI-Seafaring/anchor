# Agent configuration

ANCHOR exposes local tools through the `anchor-mcp` stdio executable. The
connected agent decides when to call those tools based on the user's request,
the MCP tool descriptions, and any project instructions supplied to the agent.

ANCHOR is not an autonomous decision-maker. It provides document, canvas, CAD,
SysML, and optional FMU operations that an MCP-capable agent can call when the
task needs project data.

## Before connecting an agent

Install ANCHOR and use one data directory consistently:

```bash
uv tool install anchor-kb
anchor serve --data-dir ~/anchor-data
```

`anchor-mcp` can run as a local stdio process without exposing a network MCP
endpoint. Keep `anchor serve` running when you want the browser UI, live canvas
updates, or canvas snapshots.

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
```

Keep this instruction short. It should guide tool selection without attempting
to encode every possible workflow.

## Claude Code

Claude Code can register a local stdio MCP server with its CLI:

```bash
claude mcp add --transport stdio --scope user anchor -- \
  anchor-mcp --data-dir ~/anchor-data --base-url http://localhost:8002
claude mcp list
```

Restart Claude Code after registration. Within a Claude Code session, run:

```text
/mcp
```

The `anchor` server should appear with its available tools. Put the optional
project instruction in `CLAUDE.md` when a repository needs it.

## Codex

Codex CLI and the Codex IDE extension share the same MCP configuration. Add
ANCHOR with:

```bash
codex mcp add anchor -- \
  anchor-mcp --data-dir ~/anchor-data --base-url http://localhost:8002
codex mcp list
```

Alternatively, add this to `~/.codex/config.toml`:

```toml
[mcp_servers.anchor]
command = "anchor-mcp"
args = ["--data-dir", "/home/you/anchor-data", "--base-url", "http://localhost:8002"]
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
        "--data-dir",
        "/home/you/anchor-data",
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

## Cursor

ANCHOR provides a Cursor helper:

```bash
anchor install cursor --data-dir ~/anchor-data
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
        "--data-dir",
        "/home/you/anchor-data",
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
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode configuration](https://opencode.ai/docs/config/)
