"""Agent-facing instructions and help text exposed by the MCP server."""

INSTRUCTIONS = """\
You're connected to Anchor, a knowledge-grounded engineering canvas.

What it is:
- This server serves one ENVIRONMENT (a named profile = the data zone). It
  holds PROJECTS; each project is a corpus (documents) plus its canvases.
- Project-scoped tools take an optional `project` argument. Omit it to use the
  default project. Use `list_projects` to see the options, `create_project` to
  make one, or `open_project` to select one for this session. Use
  `canvas_list_workspaces` to find its canvases. A missing/unknown project
  returns a self-correcting error.
- You have HTTP/MCP/CLI parity for every operation. Pick MCP from here.

Your working folder is your project (load-bearing):
- If you work in a folder (your harness's project or workspace, a repo, a
  case folder), call `create_project(folder=<its absolute path>)` once at
  the start, before you ingest anything. It returns the project that folder
  already is (or sits inside), or makes the folder a project named after it,
  and makes it this session's default. What you ingest and draw then stays
  with that folder, which is what the user expects.
- Do not fall back to the environment's `default` project just because no
  project was named. With no working folder (a chat app has none), call
  `list_projects`. If there is more than one, ask the user which one once,
  then `open_project` it and say which project you are in.
- If the user names a project, use theirs.
- "Show me Anchor", "open the canvas", "show the UI": call `canvas_url`
  (with a canvas name, or none for the project's start page) and open the
  url it returns. Never redraw a canvas as a picture or artifact of your
  own; that is not the canvas. If nothing serves the project yet,
  `canvas_url` gives the `anchor serve` command to start.
- Open the canvas once. If your harness can show a web page itself (an
  in-app browser or preview), use that and do not also launch the system
  browser; a "queued" reply from it means it is opening. Use the system
  browser only when there is no in-app one. Then say in one line what is
  open; the user is looking at it.

When an ingest comes back without gold:
- An `ingest_pdf` result with `note.gold_skipped` means no model key reached
  this server. The usual cause: the agent app was started from the Dock or
  Finder and never read the shell profile that exports the key. Tell the
  user that, and give them the exact file the note names. Never ask them to
  paste the key into the chat, and do not write it yourself.
- Do not report "no vision provider". The vision model is configured; only
  its key is missing. Say which fallback you used (`profile="text"` reads no
  figures) so the user knows to re-ingest with `force=true` once the key is in.

Source-grounding (load-bearing):
- Every value placed on the canvas should carry `data.source_ref`
  pointing back at its origin. Spec rows carry their own per-row
  source_ref. This is the project's primary trust mechanism.
- Point at the smallest thing that holds the value. A value read from a
  table cell cites that cell: `{slug, page, region_id, cell: {row,
  col}}`, with the row and col of the cell whose text is the value, as
  `get_region_content` lists them. The table's region bbox is for a row
  that quotes the whole table, not for one number in it.
- Quote the printed words that carry the value: `quotes: [{exact}]` on
  the source_ref (or `&quote=` in an `anchor:` link), copied from the page
  text. The reader sees the place highlighted and the quoted words
  underlined, in a sentence as well as in a cell or on a drawing. Add
  `prefix` / `suffix` (the words around) when the words repeat there.

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

Scoped asks (your inbox, load-bearing):
- The user can draw on a canvas and send you a remark. It waits in this
  inbox; nothing pushes it into your chat. So read the inbox at the start
  of EVERY turn in a session where Anchor is in use, not only on Anchor
  tasks: `list_pending_intents`. It is cheap, and the board shows the user
  "seen by <you>" once you have read a remark.
- The change is the reply. Add what was asked, nothing more: no extra
  cards for explanations, caveats or summaries. A caveat that matters goes
  in the thread with the change (intent_act `text`) or as one short line
  in chat. In chat, be extremely brief: one line, short words ("PX-5
  limits added, p.2. Temp range series-wide."). Never repeat what the
  canvas shows. No progress notes between tool calls.
- The canvas the user has open is the one they mean unless they name
  another. Report its remarks; sum up the rest in one line ("2 older
  remarks on other canvases"), never as a list.
- When you open or hand over a canvas, tell the user in one line that they
  can mark things on it and send them to you, and that any message to you
  (for example "check the board") makes you pick them up. Without that
  line the user sends remarks into silence.
- Take one pending intent at a time. Its `targets` name the canvas
  elements the ask is about; read them with `canvas_get_state` (filter by
  id) and `canvas_snapshot` if you want the picture.
- Reply in the thread. Ask a `question` with `intent_add_item` when the
  ask is ambiguous and wait (poll `get_intent` for the answer). Never edit
  the targeted elements with the canvas tools: change them through the
  thread.
- Show the plan first. Before you change anything, post one `message`
  per element you are about to add, with a `place` where it will land
  ("adding PX-10 dimensions table"). Each shows on the board as a ghost
  box, so the user sees how you read the ask while you work.
- Then act with `intent_act`, passing those message ids as `done`: it applies your ops at
  once and the user sees the real result with keep and put back beside it.
  This is the default. Stage instead (`apply: false`, the user approves
  before anything moves) only for a change that is large or hard to judge
  by eye, such as removing elements or rewriting many rows. Group
  dependent ops into one act; keep independent changes separate. A
  revision after feedback names the earlier suggestion in `supersedes`.
  `intent_apply` is the human's approval verb: never use it to approve your
  own staged work.
- `intent_apply` / `intent_answer` / `intent_decline` are the human's
  verbs. Do not use them to approve, answer, or decline your own staged work.
- Post a `result` item when done, then `resolve_intent`.

Tool surface (load-bearing):
- A small core is advertised by default (ingest/list/read/search docs,
  the common canvas verbs, canvas listing, project list/create/open).
  The long tail (FMU, CAD, SysML, harness ingest, advanced canvas + doc ops)
  is cataloged by `anchor_list_capabilities`. The server can dispatch those
  tools, but clients that only expose `tools/list` cannot call omitted tools.
  This server sends no `tools/list_changed` notification. Extension tools
  appear when `tools/list` is refreshed and the open project has their data.

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

Full tool reference

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
  (e.g. a doc dropped onto the canvas in a harness-ingest project, or an ask
  about a canvas selection). Pull on the IntentPending signal or your own
  cadence. Each record carries `targets`, `base_version`, and `items`.
- resolve_intent(id, result) - mark one done after you handle it.

Scoped-ask threads (#343):
- intent_add_item(id, type, text, ops?, supersedes?) - reply in a thread:
  message / question / suggestion (staged canvas ops the human approves) /
  result. Ops: {type: NodeAdded|NodeUpdated|NodeRemoved|EdgeAdded|
  EdgeUpdated|EdgeRemoved, payload}. A NodeAdded/EdgeAdded `id` is a client
  id later ops in the batch may reference.
- intent_act(id, text, ops, apply?) - the default way to make a change:
  applies at once; the human keeps it or puts it back.
- get_intent(id) - read one thread in full (states, answers).
- intent_act(id, text, ops, apply?, done?, question?, result?, resolve?) -
  post and apply a small, plain change with keep / revert available. Use
  apply: false to stage it for human review instead.
- intent_answer / intent_apply / intent_decline - the human's verbs
  (gated under `intent_threads`); intent_ask opens a thread on a selection.

Status tools:
- anchor_status: show cwd, config path, data dir, and document/canvas counts
- anchor_extension_status: show bundled runtime availability and failure reasons,
  plus discovered OIP producers with a PATH check on their invocation.command
  (never started by Anchor; the harness spawns them)

PDF tools (extension anchor_pdfs):
- ingest_pdf / list_documents / get_document_index
- search_documents - semantic search across embedded gold regions
- get_gold_regions / get_page_text / get_page_image / get_crop / get_pdf
  (get_crop takes rel_path '<page>/<region_id>.png' and renders the crop
  lazily from the bronze PDF; both image tools take an optional dpi, 72-600)
- locate_text - where a value appears on a page (page-space quads), for value-precise highlights

Harness ingestion (provider = harness, no API key):
- ingest_begin / ingest_get_page / ingest_submit_page
- ingest_status (resume by slug) / ingest_finalize / ingest_abort
You (the agent) polish each page and group regions by candidate item
ids; the server validates, computes bboxes, embeds, and publishes
atomically on finalize.

FMU tools (anchor_fmus, optional): fmu_inspect / fmu_list_models / fmu_simulate / ...
CAD tools (anchor_cad): inspect / list_models / set_parameter / ...
SysML tools (anchor_sysml): sysml_render / sysml_export

Placeholder protocol

A placeholder node carries `data.placeholder == true` and optionally
`data.placeholder_hint == "<what we want here>"`. Visual: dashed
sky-blue outline + hint chip. Agent: enumerate via
`canvas_list_placeholders`, fill via `canvas_update_node({id, data: {
placeholder: false, source_ref: {slug, page, bbox, region_id?, item_id?,
cell?}, rows: [
{key, value, source_ref}, ... ]}})`. Keep `placeholder_hint` in `data`
even after filling. It is useful audit history.

Where data lives

Each project is a folder with a hidden `.anchor_data/` holding its corpus.
A project you create here is managed under the environment:

~/.anchor/envs/<env>/projects/<project>/.anchor_data/
  bronze/<slug>/<sha256>.pdf
  silver/<slug>/{index.json, pages/}
  gold/<slug>/{pages/<n>.regions.json, pages/<n>/<region-id>.png}
  canvases/<slug>/{meta.json, state.json, events.jsonl}

A project a human created with `anchor init` keeps the same `.anchor_data/`
inside their working folder; the environment's `projects.toml` maps each
project name to its folder, so you address them all by name regardless.
"""
