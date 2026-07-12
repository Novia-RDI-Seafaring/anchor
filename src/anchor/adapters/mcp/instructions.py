"""Agent instructions and help text published by the MCP adapter."""

from __future__ import annotations

INSTRUCTIONS = """\
You're connected to Anchor, a knowledge-grounded engineering canvas.

What it is:
- This server serves one ENVIRONMENT (a named profile = the data zone). It
  holds PROJECTS; each project is a corpus (documents) plus its canvases.
- Project-scoped tools take an optional `project` argument. Omit it to use the
  default project. Use `list_projects` to see the options, `create_project` to
  make one. A missing/unknown project returns a self-correcting error.
- You have HTTP/MCP/CLI parity for every operation. Pick MCP from here.

Source-grounding (load-bearing):
- Every value placed on the canvas should carry `data.source_ref`
  pointing back at its origin (page+bbox for PDFs, region_id for
  gold-extracted regions). Spec rows carry their own per-row
  source_ref. This is the project's primary trust mechanism.

When the user asks you to populate placeholders:
1. `canvas_list_placeholders(workspace_slug)` returns the ones flagged.
2. For each, use `search_documents` (semantic) or `get_gold_regions`
   to find the answer.
3. Replace the placeholder by writing real data via
   `canvas_update_node({id, label, data: {placeholder: false,
   source_ref: ..., rows: [...]}})`.
4. Optionally call `canvas_organize_subtree` to tidy the result.

If you're producing a snapshot of the canvas, use `canvas_snapshot(...,
format: "inline")` so the host renders the image inline.

Tool surface (load-bearing):
- A small core is advertised by default (ingest/list/read/search docs,
  the common canvas verbs, project list/create). The long tail (FMU, CAD,
  SysML, the harness ingest sub-protocol, advanced canvas + doc ops) is
  reachable but not advertised until needed. Call `anchor_list_capabilities`
  to see it; every listed tool is callable by name straight away. Extension
  tools also auto-appear once the open project has data for them.

Stuck? Read the `anchor://help` resource for the deeper tour.

Project resolution check:
- If visible data looks wrong, call `list_projects` to see this environment's
  projects, and pass the right one as the `project` argument. Call
  `anchor_status` to confirm the resolved environment and data dir.
- This server is one environment (one data zone). To use a different
  environment, the user adds a second named MCP server (`anchor-mcp --env
  <name>`). You cannot cross environments from here.
"""


HELP_RESOURCE_TEXT = INSTRUCTIONS + """

--- Full tool reference ---

Canvas tools:
- canvas_list_workspaces / canvas_create_workspace / canvas_get_state
- canvas_add_node / canvas_update_node / canvas_remove_node
- canvas_add_edge / canvas_update_edge / canvas_remove_edge
- canvas_clear / canvas_organize_subtree / canvas_align / canvas_distribute
- canvas_create_sub_canvas - nest a child canvas inside a node
- canvas_list_placeholders - your "what to fill" entrypoint
- canvas_snapshot - PNG of the live canvas; pass format='inline'

Agent intent queue (your inbox, issue #148):
- list_pending_intents / next_intent - user canvas actions waiting for you
  (e.g. a doc dropped onto the canvas in a harness-ingest project). Pull on the
  IntentPending signal or your own cadence.
- resolve_intent(id, result) - mark one done after you handle it.

Status tools:
- anchor_status: show cwd, config path, data dir, and document/canvas counts
- anchor_extension_status: show bundled runtime availability and failure reasons

PDF tools (extension anchor_pdfs):
- ingest_pdf / list_documents / get_document_index
- search_documents - semantic search across embedded gold regions
- get_gold_regions / get_page_text / get_page_image / get_crop / get_pdf
- locate_text - where a value appears on a page (page-space quads), for
  value-precise highlights

Harness ingestion (provider = harness, no API key):
- ingest_begin / ingest_get_page / ingest_submit_page
- ingest_status (resume by slug) / ingest_finalize / ingest_abort
You (the agent) polish each page and group regions by candidate item
ids; the server validates, computes bboxes, embeds, and publishes
atomically on finalize.

FMU tools (anchor_fmus, optional): fmu_inspect / fmu_list_models / fmu_simulate / ...
CAD tools (anchor_cad): inspect / list_models / set_parameter / ...
SysML tools (anchor_sysml): sysml_render / sysml_export

--- Placeholder protocol ---

A placeholder node carries `data.placeholder == true` and optionally
`data.placeholder_hint == "<what we want here>"`. Visual: dashed
sky-blue outline + hint chip. Agent: enumerate via
`canvas_list_placeholders`, fill via `canvas_update_node({id, data: {
placeholder: false, source_ref: {slug, page, bbox, region_id?}, rows: [
{key, value, source_ref}, ... ]}})`. Keep `placeholder_hint` in `data`
even after filling. It is useful audit history.

--- Where data lives ---

Each project is a folder with a hidden `.anchor_data/` holding its corpus.
A project you create here is managed under the environment:

~/.anchor/envs/<env>/projects/<project>/.anchor_data/
  bronze/<filename>.pdf
  silver/<slug>/{index.json, pages/}
  gold/<slug>/{pages/<n>.regions.json, pages/<n>/<region-id>.png}
  canvases/<slug>/{meta.json, state.json, events.jsonl}

A project a human created with `anchor init` keeps the same `.anchor_data/`
inside their working folder; the environment's `projects.toml` maps each
project name to its folder, so you address them all by name regardless.
"""
