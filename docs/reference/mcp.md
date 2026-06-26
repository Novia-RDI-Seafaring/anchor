# MCP tools

`anchor-mcp` exposes ANCHOR over MCP stdio for local agent harnesses. The
tools available at runtime include canvas operations and bundled extension
tools; optional FMU behavior depends on installed/runtime configuration.

## Connect an agent harness

One MCP server serves one **environment** (a named profile = the data zone),
selected by name. Projects inside it are addressed by a per-call `project`
argument.

```bash
anchor install claude-code              # writes the MCP entry + skill (default env)
anchor install claude-desktop --env work
anchor install cursor --env work
```

Each writes an entry that runs `anchor-mcp --env <name>`:

```bash
anchor-mcp --env work
```

Project-scoped tools take an optional `project`; omit it for the default
project. `list_projects` enumerates the environment's projects, `create_project`
makes one, and a missing/unknown project returns a self-correcting error. A
second environment is a second named server (Claude Desktop supports `--name`);
the agent cannot cross from one environment into another.

See [Environments and projects](../guides/environments-and-projects.md) and
[Agent configuration](../guides/agent-configuration.md) for Codex, OpenCode,
and generic stdio client examples.

## Tool families

| Family | Representative operations |
| --- | --- |
| Status | `anchor_status` |
| Environment / projects | `list_projects`, `create_project`, `update_project`, `open_project`, `create_environment` |
| Canvas | `canvas_list_workspaces`, `canvas_get_state`, `canvas_add_node`, `canvas_update_node`, `canvas_add_edge`, `canvas_node_types`, `canvas_snapshot` |
| Documents | `ingest_pdf`, `list_documents`, `get_document_index`, `get_gold_regions`, `search_documents`, `get_crop` |
| Harness ingestion | `ingest_begin`, `ingest_get_page`, `ingest_submit_page`, `ingest_status`, `ingest_finalize`, `ingest_abort` - the agent performs polish + region grouping page by page (provider `harness`, no API key); CLI parity via `anchor ingest-session` |
| CAD | `inspect`, `list_models`, `set_parameter` |
| SysML | `sysml_render`, `sysml_export` |
| FMU | Inspection and simulation tools when enabled by the bundled FMU extension. |

## Status check

Use `anchor_status` when an MCP client appears connected but sees the wrong
documents or an empty canvas list. It reports the resolved environment, the
active project's data directory, and document / embedding / workspace counts.

If it shows the wrong project, pass the right `project` argument (see
`list_projects`). To use a different environment, add a second named server
(`anchor-mcp --env <name>`); the agent cannot switch environments on its own.

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
