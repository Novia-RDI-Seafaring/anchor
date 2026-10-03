# MCP tools

`anchor-mcp` exposes local ANCHOR tools over MCP stdio. It is launched by your
agent client and operates on the same project files as the CLI and browser.

## Environment and project selection

```bash
anchor install codex --env study
```

Built-in installers also support `claude-code`, `claude-desktop`, and `cursor`.
Each registers a command equivalent to `anchor-mcp --env study`. One server
serves that environment's projects. Select a project with `open_project(name)`
or pass `project="pump-study"` on project-scoped calls. Before a session
selection, omitted project arguments use `default`. `anchor use` affects CLI
defaults only.

Call `list_projects` and `anchor_status` when data looks empty or wrong. Add a
second named server to access another environment. See
[Agent setup](../guides/agent-setup.md) and
[manual configuration](../guides/agent-configuration.md).

## Discover the full surface

The initial advertised tool list is a small core. Call
`anchor_list_capabilities` to discover the long tail. Listed tools are callable
by name even when they were omitted from the initial list; applicable extension
tools may also appear when a project contains their data.

The server supplies connection instructions and the `anchor://help` resource.
Claude Code's installer additionally writes a composed skill. Codex and Claude
Desktop installers register MCP entries without a separate skill file.

| Family | Representative operations |
| --- | --- |
| Discovery and status | `anchor_list_capabilities`, `anchor_status` |
| Environment and projects | `list_projects`, `create_project`, `update_project`, `open_project`, `create_environment` |
| Canvas | `canvas_list_workspaces`, `canvas_create_workspace`, `canvas_get_state`, `canvas_add_node`, `canvas_update_node`, `canvas_add_edge`, `canvas_node_types`, `canvas_snapshot` |
| Intent inbox and threads | `list_pending_intents`, `next_intent`, `get_intent`, `intent_add_item`, `resolve_intent` |
| Human intent decisions | `intent_answer`, `intent_apply`, `intent_decline`, `intent_revert` |
| Proposal sets | `canvas_propose_set`, `canvas_add_to_proposal_set`, `canvas_list_proposal_sets`, `canvas_review_proposal_set` |
| References | `canvas_create_reference`, `canvas_list_references`, `canvas_remove_reference`, `canvas_update_reference`, `canvas_attach_reference` |
| Documents | `ingest_pdf`, `list_documents`, `get_document_index`, `get_gold_regions`, `search_documents`, `get_crop` |
| Harness ingestion | `ingest_begin`, `ingest_get_page`, `ingest_submit_page`, `ingest_status`, `ingest_finalize`, `ingest_abort` |
| CAD and SysML | `inspect`, `list_models`, `set_parameter`, `sysml_render`, `sysml_export` |
| FMU | Inspection and simulation tools; simulation requires its optional runtime. |

Use the live schemas for argument names and required fields. The table summarizes
families rather than listing every operation.

## Process a submitted canvas request

1. Pull `list_pending_intents` for the project at the start of an ANCHOR task
   and when prompted to check the inbox.
2. Read the selected intent, its target objects, and relevant document evidence.
3. Reply through `intent_add_item`. Use a question when requirements are unclear,
   or a suggestion with staged operations and a rationale for a proposed edit.
4. Wait for the human's answer or decision. An agent should not call the human
   decision tools to approve its own suggestion.
5. Post the result and resolve the intent after handling it.

The browser can signal a pending count, but ANCHOR does not launch your agent
or guarantee background polling by your client. Intents are project-scoped and
include their origin canvas and target elements. Marking a node as a placeholder
does not enqueue a task.

An upload in a `harness` project creates a `drop_to_ingest` intent. Process its
page-by-page session, update the document card, and resolve the intent. Built-in
`ingest_pdf` alone does not perform the harness's interpretation stage.

## Write source-linked tables

Search gold regions when available, or read page text and stored layout geometry.
Put a `source_ref` on each spec row. A page, region, item, cell, or explicit box
provides different source precision; use the most precise supported locator
available. PDF boxes use points, a top-left origin, and
`[left, top, right, bottom]`.

A row citation does not grant Verified status by itself. The server matches
claims to stored validated evidence; caller-supplied evidence verdicts do not
establish a binding. Rows are whole-list replacements on update, so include all
rows to retain. See [Claim and evidence](../concepts/claim-evidence.md) and
[Source resolution](../concepts/spec-source-resolution.md).

## Transport and snapshot limits

`anchor serve` supplies the browser UI, HTTP API, and SSE; it does not expose a
hosted authenticated MCP HTTP endpoint. MCP uses a separate stdio process.
Event buses and write locks are process-local. Avoid simultaneous mutations to
the same canvas from separate processes; re-read state when clients disagree.

Canvas snapshots need a running server for the requested project and Chromium.
Use `format="inline"` for image-capable clients. Set `--base-url` to the actual
server URL if it uses another port.
