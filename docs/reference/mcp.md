# MCP tools

`anchor-mcp` exposes ANCHOR over MCP stdio for local agent harnesses. The
tools available at runtime include canvas operations and bundled extension
tools; optional FMU behavior depends on installed/runtime configuration.

## Connect an agent harness

The simplest path registers a **folder-resolving** server once — it works for
every `anchor init` project, because it resolves the project from the directory
the agent is launched in:

```bash
anchor install claude-code   # writes the MCP entry + skill, no baked data dir
anchor install cursor
```

`anchor install claude-code` targets Claude Code. Claude Desktop reads a
separate `claude_desktop_config.json`, so configure that client with an
`mcpServers.anchor` entry that runs `anchor-mcp`.

Then open the agent inside a project folder (one with an `anchor.toml`) and the
tools target that project. To name a project explicitly — for example when the
server's working directory is elsewhere — pass `--project`:

```bash
anchor-mcp --project /path/to/project
```

See [Agent configuration](../guides/agent-configuration.md) for Codex,
OpenCode, and generic stdio client examples.

## Tool families

| Family | Representative operations |
| --- | --- |
| Status | `anchor_status` |
| Canvas | `canvas_list_workspaces`, `canvas_get_state`, `canvas_add_node`, `canvas_update_node`, `canvas_add_edge`, `canvas_snapshot` |
| Documents | `ingest_pdf`, `list_documents`, `get_document_index`, `get_gold_regions`, `search_documents`, `get_crop` |
| Harness ingestion | `ingest_begin`, `ingest_get_page`, `ingest_submit_page`, `ingest_status`, `ingest_finalize`, `ingest_abort` - the agent performs polish + region grouping page by page (provider `harness`, no API key); CLI parity via `anchor ingest-session` |
| CAD | `inspect`, `list_models`, `set_parameter` |
| SysML | `sysml_render`, `sysml_export` |
| FMU | Inspection and simulation tools when enabled by the bundled FMU extension. |

## Status check

Use `anchor_status` when an MCP client appears connected but sees the wrong
documents or an empty canvas list. It reports:

- the process working directory
- the resolved `anchor.toml`, if one was found
- the active data directory
- document, embedding, and workspace counts

If the paths do not match the project you intended, restart the client from the
project folder or configure `anchor-mcp --project /path/to/project`.

## Source-grounded workflow

1. Call `canvas_list_placeholders` for a workspace.
2. Find relevant material through `search_documents` or
   `get_gold_regions`.
3. Update the target node with `placeholder: false` and a `source_ref`.
4. Use `canvas_organize_subtree` or alignment helpers if the result needs
   layout cleanup.

For snapshots, keep `anchor serve` running and call `canvas_snapshot` with
`format="inline"` when your MCP client supports displayed images.

## Transport boundary

The packaged MCP server is stdio-based. `anchor serve` exposes the browser UI,
HTTP API and SSE updates; it does not provide a hosted authenticated MCP HTTP
endpoint.
