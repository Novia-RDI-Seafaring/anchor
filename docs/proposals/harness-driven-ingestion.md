> Superseded (shipped in 0.2.5): harness-driven ingestion is now implemented. See `IngestSessionService`, the `ingest_begin` / `ingest_submit_page` / `ingest_finalize` operations on MCP, HTTP, and CLI, and the `harness` provider in `anchor init`.

# Harness-driven ingestion (no-API-key ingest via the harness agent)

Status: proposal
Tracking issue: [#99](https://github.com/Novia-RDI-Seafaring/anchor/issues/99)

## Summary

Add an opt-in ingestion mode where the harness agent (Claude Code, or any
MCP- or CLI-capable agent) performs the two cognitive pipeline steps
itself: page-markdown polish and gold region extraction. Anchor keeps every
mechanical step (docling extraction, page PNG rendering, local bge
embeddings, validation, persistence) and exposes a transactional
work-order protocol the agent follows page by page. The result: a user
whose only AI is the harness they are already talking to can get full
gold-layer ingestion with zero API keys and zero new egress.

The built-in key-based pipeline stays. Harness mode is a third leg, not a
replacement: keyed providers for headless and batch, local/ollama for
self-hosted vision, harness for "I have Claude Code and nothing else".

## Motivation

Every onboarding pain testers hit traces back to the OpenAI-compatible
key:

- `anchor init` has to walk users through provider, endpoint, key
  placement, and `.env` hygiene (`src/anchor/adapters/cli/init.py`).
- `anchor check` exists largely to probe that the key and endpoint
  actually work (`src/anchor/adapters/cli/check.py`).
- Without a key, polish and regions silently no-op: the CLI wiring
  passes `polisher=None, region_extractor=None`
  (`src/anchor/adapters/cli/services.py`), gold never materialises, and
  the skill has to document the failure mode ("gold extraction skipped ->
  no ANCHOR_OPENAI_API_KEY set",
  `src/anchor/skills/extensions/anchor_pdfs/skill.md`).

Meanwhile the user is, by definition, already running a capable
vision-and-text model: the harness agent itself. The agent can read page
images through the existing byte-fetch envelope and write structured
output through MCP tools. What is missing is a protocol that makes this
safe: server-side validation, transactional visibility, resumability.

## Current state, with file references

### Where the LLM is called today

`IngestService.ingest_pdf`
(`src/anchor/extensions/anchor_pdfs/core/services.py:127`) runs:

1. bronze stash, docling extract, silver index + `pages.meta.json` +
   per-page `N.raw.md`, page PNG render (mechanical, no LLM).
2. Polish loop (`services.py:222-254`): per page, calls the
   `PageMdPolisher` port with `(page_image: bytes, page_no, deterministic_md,
   docling_items, model)` and gets back a markdown string, written to
   `silver/<slug>/pages/<n>.md`. The OpenAI impl
   (`infra/llm/openai_md_polisher.py`) sends the base64 page PNG, the
   deterministic markdown seed, and up to 8000 chars of docling items.
3. Region loop (`services.py:256-300`): per page, calls the
   `RegionExtractor` port with the same inputs and gets back a list of
   region dicts. The OpenAI impl
   (`infra/llm/openai_region_extractor.py`) prompts for
   `id, kind (chart|spec_block|table|figure|diagram|text), title,
   description, approximate bbox [left, top, right, bottom] in BOTTOMLEFT
   coords, tags[], entities[]` under a JSON key `regions`. Each returned
   bbox is snapped to docling items via `snap_to_docling_items`
   (`core/silver.py:331`), then persisted with
   `write_gold_region_file` to `gold/<slug>/pages/<n>.regions.json`.
4. Embedding (`services.py:302-313` and `embed_document`): embeds
   `"{title}. {description}"` per region with the configured embedder.
   The default is the local `BAAI/bge-small-en-v1.5`
   sentence-transformer; `build_embedder`
   (`infra/llm/embedder_selection.py`) only picks the OpenAI embedder for
   `text-embedding-*` model ids. Embeddings stay local even when a key is
   present.

Only steps 2 and 3 need an LLM. Both ports already receive exactly the
inputs an agent would need (page image, deterministic markdown, docling
items) and return plain data (a string; a list of dicts). The seam is
clean.

### Validation today: effectively none

- `services.py:268-279` only snaps bboxes; every other field of a region
  dict is persisted as-is.
- `FsDocStore.write_gold_region_file`
  (`infra/fs_doc_store.py:189`) writes whatever it gets, with one
  normalisation: aliasing `approximate_bbox` to `bbox`.
- The OpenAI region extractor swallows malformed model output and
  returns `[]` (`infra/llm/openai_region_extractor.py:60-69`), so a page
  can silently end up with zero regions and no error.
- No check on `kind` against the documented enum, no bbox bounds check
  against the page, no required-field check.

Any harness protocol must add the validation the current pipeline lacks,
and the validation should be shared so the keyed pipeline benefits too.

### Visibility and idempotency today: leaky

- `has_gold` is directory existence:
  `(gold/<slug>/pages).is_dir()` (`infra/fs_doc_store.py:75`). Region
  files are written per page inside the loop (`services.py:279`), so a
  crash mid-gold leaves a document that `list_documents` reports as
  `has_gold: true` with a partial region count.
- The idempotency gate (`services.py:149`) checks
  `get_gold_map(slug) is not None`, but `get_gold_map`
  (`infra/fs_doc_store.py:120-133`) returns non-None whenever
  `silver/<slug>/index.json` exists, even with zero regions. A
  silver-only document (ingested with `--skip-regions`, or after a
  mid-gold crash) is treated as "already ingested (gold exists)" and
  re-ingest is refused without `--force`.

A multi-turn harness protocol makes partial state the common case, not
the crash case, so these gaps go from latent to load-bearing. The
protocol below fixes them with a staging area and an atomic publish.

### What silver already gives the agent

Docling emits per-block layout items: `label, page, bbox, text` (plus
`cells` for tables), flattened in
`infra/pdf/docling_extractor.py:_flatten` and consumed by the pure
builders in `core/silver.py`. Bboxes are BOTTOMLEFT
`[left, top, right, bottom]` with `top > bottom`, and the repo already
has the geometry helpers (`union_bbox`, `point_in_bbox`,
`snap_to_docling_items` in `core/silver.py:304-354`).

These items are exactly the candidate boxes the agent needs: instead of
emitting free-form pixel coordinates from looking at a PNG, the agent
groups item ids and the server computes the union bbox. `pages.meta.json`
(`core/silver.py:226`) already mints stable per-item ids
(`p{page}-i{idx}`), but it stores only counts, label histograms, and the
page bbox union; the items themselves (id, label, bbox, text) are held in
memory during ingest and never persisted. Harness mode needs them on
disk, both as work-item payload and so a session survives a crash.

### Protocol precedents already in the repo

- Placeholder-node protocol: drop-to-ingest places a placeholder
  document node with `data.status` in {pending, ingesting, ready,
  failed} and finalizes it when the pipeline completes
  (`extensions/anchor_pdfs/adapters/http/upload.py`); the canvas skill
  documents `canvas_list_placeholders` as the agent entry point.
- Idempotent ingest + `force` (`services.py:144-156`, CLI `--force`).
- Append-only `events.jsonl` per workspace with replay on cold boot
  (`infra/stores/fs_workspace_store.py`, `infra/bus/replay.py`); the
  session journal below reuses the same shape.
- Byte-fetch envelope: binary reads return `{format: path|base64, ...}`
  so same-host agents read the path and remote agents inline base64
  (`extensions/anchor_pdfs/mcp_handlers.py:_byte_envelope`).

## Protocol design

### Roles

- Anchor (trusted side): runs every deterministic step, owns the schema,
  validates every submission, controls visibility, persists atomically.
- Harness agent (cognitive side): reads work items, looks at page
  images, writes polished markdown and grouped regions, never touches
  the data dir directly.

### Operations

All operations land on core (`IngestSessionService`, a sibling of
`IngestService` in `extensions/anchor_pdfs/core/`), and reach MCP, HTTP,
and CLI in the same PR per the adapter parity rule.

`ingest_begin(pdf_path, slug?, dpi?, force?) -> WorkOrder`

Runs bronze + docling + silver index/meta/raw-md + page PNGs (the
mechanical front half of `ingest_pdf`), persists per-page candidate
items to the session, and opens a session. Returns:

```json
{
  "session_id": "ing-7f3a...",
  "slug": "alfa-laval-lkh",
  "protocol_version": 1,
  "page_count": 8,
  "pages": [
    {"page": 1, "candidate_count": 23, "needs_polish": true,
     "status": "pending"}
  ],
  "submit_schema_digest": "sha256:..."
}
```

Idempotency: if the slug already has *published* gold, return
`{skipped: true}` unless `force`, matching today's contract. If an open
session already exists for the slug, return that session (resume) instead
of starting a second one.

`ingest_get_page(session_id, page, format=path|base64) -> WorkItem`

```json
{
  "page": 3,
  "image": {"format": "path", "value": ".../silver/<slug>/pages/3.png",
             "content_type": "image/png"},
  "raw_md": "# LKH Centrifugal Pump...",
  "candidates": [
    {"id": "p3-i0", "label": "section_header",
     "bbox": [56.0, 712.4, 388.2, 690.1], "text": "Technical data"},
    {"id": "p3-i1", "label": "table", "bbox": [56.0, 680.0, 540.0, 420.0],
     "text": "", "cells_preview": {"shape": {"rows": 12, "cols": 3},
                                     "header_row": ["", "50 Hz", "60 Hz"]}}
  ],
  "instructions": "...the per-page task statement, versioned...",
  "status": "pending"
}
```

The image reuses the byte-fetch envelope: same-host harnesses (the
normal case) get a path and read the PNG with their own file tools;
remote ones request base64. A batched variant
`ingest_get_pages(session_id, pages[])` keeps turn count down for
subagent fan-out.

`ingest_submit_page(session_id, page, polished_md?, regions[]) -> Verdict`

A submitted region names geometry by grouping, not by pixels:

```json
{
  "kind": "spec_block",
  "title": "Technical data",
  "description": "Max flow, head, and motor sizes for LKH-5 to LKH-90",
  "member_item_ids": ["p3-i0", "p3-i1"],
  "tags": ["specs"],
  "entities": ["LKH-5"],
  "approx_bbox": null
}
```

Server-side validation (the trusted side enforces the contract):

- `kind` must be in the documented enum.
- `member_item_ids` must exist on that page of that session; the server
  computes `bbox = union_bbox(member bboxes)` (BOTTOMLEFT), so the agent
  never emits free-form coordinates.
- Escape hatch: when docling missed a visual (a chart rendered as a
  single picture block, or nothing at all), the agent may send
  `approx_bbox` instead of members; the server snaps it with
  `snap_to_docling_items` and falls back to the clamped coarse box,
  stamping the region `geometry: "snapped"` or `"coarse"` so consumers
  can see the provenance difference.
- `title` required and non-empty; lengths bounded; unknown fields
  rejected (closed schema).
- `polished_md` sanity checks: non-empty when `needs_polish`, bounded
  size, optional fidelity heuristic (a floor on overlap with the raw
  markdown's token set) to catch hallucinated rewrites.
- Bad submissions return structured errors
  (`{accepted: false, errors: [{region_index, field, message}]}`) so the
  agent can repair and resubmit without a human in the loop.

Per-page submissions are idempotent: resubmitting a page replaces that
page in staging. Everything goes to staging only; the verdict reports
`remaining_pages`.

`ingest_status(session_id | slug) -> SessionStatus`

`{state: open|finalizing|published|aborted, pages: [{page, status}],
started_at, updated_at, protocol_version}`. This is the resume surface:
after a crash or a context compaction, the agent (or a fresh agent) calls
status, sees which pages are pending, and continues. Keyed by slug too,
so "continue ingesting alfa-laval-lkh" works without remembering ids.

`ingest_finalize(session_id, allow_missing_pages?) -> Summary`

- Completeness check: every page submitted (or explicitly listed in
  `allow_missing_pages`); otherwise a structured refusal naming the
  pending pages.
- Runs local bge embeddings over the staged regions (reusing
  `embed_document` against the staging store).
- Publishes atomically: staged silver page markdown and gold region
  files are moved into `silver/<slug>/` and `gold/<slug>/` with directory
  renames, then the session is marked `published`. Only now do
  `list_documents`, `get_gold_map`, and `search_documents` see the doc's
  gold.
- Writes `ingest-report.json` with `mode: "harness"`, the
  harness-declared model id, protocol version, and per-page timings,
  mirroring today's report (`services.py:316-341`).
- Emits the same `DocPolished` / `DocGoldExtracted` / `DocIngested`
  events so the canvas placeholder flow keeps working unchanged.

`ingest_abort(session_id) -> {aborted: true}`

Discards staging. Bronze and the mechanical silver artifacts may stay
(they are deterministic and cheap to keep); the doc remains exactly as
ingestable as before the session.

### Session storage and transaction semantics

```
<data_dir>/staging/ingest/<session_id>/
  session.json          # slug, state, protocol_version, page statuses
  journal.jsonl         # append-only: begin/submit/finalize/abort entries
  candidates/<n>.json   # docling items (id, label, bbox, text) per page
  silver/pages/<n>.md   # staged polished markdown
  gold/pages/<n>.regions.json
```

- Nothing under `staging/` is scanned by `FsDocStore.list_documents`,
  so nothing is visible to list/search until finalize.
- `journal.jsonl` follows the `events.jsonl` precedent: state is a fold
  of the journal, so resume after a crash is a replay, and concurrent
  double-submits resolve last-writer-wins per page.
- Finalize is the only operation that mutates `silver/` and `gold/`,
  and it does so via staged-directory renames so a crash during publish
  leaves either the old state or the new state, not a blend.
- While fixing visibility for harness mode, the same completeness marker
  (a `gold/<slug>/.complete` stamp or a field in the ingest report)
  should replace the `is_dir()` check behind `has_gold` and the
  `get_gold_map is not None` idempotency gate, closing the existing
  partial-gold leak for the keyed pipeline too.

### Subagent fan-out

Pages are independent by construction: a work item references only its
own page's image, markdown, and candidates, and submissions are per-page
idempotent. The skill should instruct the orchestrating agent to:

- call `ingest_begin`, read `page_count`;
- for small docs (<= 4 pages), just loop in the main context;
- for larger docs, spawn subagents, each given the `session_id` and a
  contiguous batch of 3-5 pages, instructed to
  `ingest_get_pages -> read image -> ingest_submit_page` per page and
  return only the verdict summaries;
- after all subagents return, call `ingest_status` to verify nothing is
  pending, then `ingest_finalize`;
- on any interruption, re-enter via `ingest_status(slug)`.

### Provider "harness" in init / check / status

Add a `harness` entry to the provider registry
(`src/anchor/infra/providers.py`): zone "on-host; pages are read by the
agent harness you are already running", `does_vision` true but served by
the protocol, no base URL, no key. `anchor init --provider harness`
writes `anchor.toml` with zero secrets and skips the key setup path
entirely (`_setup_api_key` already gates on `_KEYED_PROVIDERS`).
`anchor check` skips the endpoint probe and instead reports whether the
harness protocol surface is reachable (the MCP/CLI ops exist) and
whether any sessions are open. `anchor list` / status surfaces should
label harness-ingested documents from the report's `mode` field, e.g.
`gold: 41 regions (harness: claude-fable-5)`.

### Adapter parity

Per the repo rule, all six operations ship on all three surfaces in the
implementing PR:

- MCP: `ingest_begin`, `ingest_get_page(s)`, `ingest_submit_page`,
  `ingest_status`, `ingest_finalize`, `ingest_abort` in
  `extensions/anchor_pdfs/mcp_handlers.py`.
- HTTP: `POST /api/ingest/sessions`, `GET .../sessions/{id}/pages/{n}`,
  `PUT .../sessions/{id}/pages/{n}`, `GET .../sessions/{id}`,
  `POST .../sessions/{id}/finalize`, `DELETE .../sessions/{id}`.
- CLI: `anchor ingest begin <pdf>`, `anchor ingest page <session> <n>`,
  `anchor ingest submit <session> <n> --file page3.json`,
  `anchor ingest status <session|slug>`, `anchor ingest finalize`,
  `anchor ingest abort`. JSON in, JSON out, so any shell-capable harness
  (Codex CLI, a cron-driven script wrapping a model, a human with jq)
  can run the protocol without MCP.

### Security and egress

- Harness mode adds zero egress paths. Page images and text go only to
  the harness process, which already has filesystem access to the data
  dir; where the harness sends them is governed by the harness's own
  provider agreement, which the user accepted when they installed it.
  `anchor init` should state this in the zone line.
- The HTTP server stays unauthenticated loopback-only; sessions add
  write surface, so session ids must be unguessable (random, not
  sequential) and slugs revalidated through `validate_workspace_slug` /
  `safe_upload_name` as today.
- Server-side validation is the trust boundary: the harness is treated
  as a competent but unverified worker. Nothing it submits is persisted
  to the published layers without passing the closed schema, and the
  computed-bbox rule means it cannot place provenance boxes at arbitrary
  coordinates.

## Quality stance

Output quality varies with the harness model, and that is acceptable for
an opt-in mode. The trade is explicit: a tester with no key gets gold
extraction at whatever quality their harness model delivers, with the
mode and model recorded in `ingest-report.json` and surfaced by status.
The keyed pipeline remains the recommendation for headless servers,
batch ingestion, and reproducible quality, because it runs without an
interactive agent and with a pinned model.

## Phased implementation plan

Sized as one PR each, in dependency order:

1. `feat(ingest): persist per-page docling candidate items + shared
   region schema validation`. Write `candidates` (id, label, bbox,
   text) to silver during ingest; add a pure `core` validation module
   (kind enum, bbox bounds, required fields) and apply it in the keyed
   region loop too. Fixes the silent-unvalidated-gold gap on its own.
2. `feat(ingest): completeness marker for gold`. Replace the
   `is_dir()` `has_gold` and the `get_gold_map` idempotency gate with an
   explicit completeness stamp; keyed pipeline writes it at the end of
   the region loop. Migration: stamp existing docs that have regions.
3. `feat(ingest): IngestSessionService + staging store`. Core service,
   session/journal/staging layout, begin/get/submit/status/finalize/
   abort against the DocStore port, with memory-store tests for resume,
   idempotent resubmit, atomic publish, abort.
4. `feat(ingest): harness protocol on MCP, HTTP, CLI`. The six
   operations on all three surfaces, with the byte envelope on work
   items and structured validation errors.
5. `feat(init): provider "harness"`. Registry entry, init flow with no
   key step, check/status reporting, config plumbing.
6. `docs(skill): harness ingestion protocol + subagent fan-out`. Skill
   sections (protocol walkthrough, fan-out instructions, resume ritual),
   `docs/guides/` walkthrough, MCP/CLI reference updates.

Each PR is independently shippable; 1 and 2 improve the existing
pipeline even if the rest stalls.

## Risks and open questions

- Docling misses a region entirely (a full-bleed chart, a scanned
  drawing with no text blocks). The grouping rule then has no members to
  union. The `approx_bbox` escape hatch covers it, but coarse boxes
  degrade provenance; the `geometry` stamp keeps that honest. Open
  question: should `finalize` warn when a page has zero regions and a
  high picture count?
- Cost and latency in the harness. A 40-page manual is at minimum 40
  get/submit pairs plus image reads; in a single context that competes
  with the user's session budget. Mitigations: batched
  `ingest_get_pages`, multi-page submit, subagent fan-out, and the
  `needs_polish` heuristic (`core/silver.py:357`) to skip polish on
  simple pages. Still expected to be slower than the keyed pipeline.
- Protocol drift between skill text and server. The work order carries
  `protocol_version` and the per-page `instructions` text comes from the
  server, not the skill, so the skill only teaches the loop shape; the
  server owns the task statement. Submissions with a mismatched
  `protocol_version` are rejected with a "re-run ingest_begin" error.
- Partial-failure UX. A half-submitted session must be visible and
  actionable: `ingest_status(slug)` from a fresh conversation, `anchor
  check` listing open sessions with age, and a stale-session policy
  (auto-abort after N days?) are needed so staging does not accumulate.
- Concurrent sessions on one slug. Proposed rule: one open session per
  slug; `ingest_begin` returns the existing session for resume. Does a
  `force` begin abort the open session or refuse?
- Embedding text quality depends on harness-written titles and
  descriptions; weak descriptions degrade `search_documents`. The
  validation floor (non-empty, bounded) is necessary but not
  sufficient; the skill should show one good and one bad example.
- The HTTP surface is unauthenticated; staging adds a write path on
  loopback. Acceptable under the current security model, but worth
  rechecking if the server ever binds beyond loopback.

## Alternatives considered

- Ship a local VLM as a dependency (extend the existing ollama
  provider with a bundled model). Keeps the pipeline shape, but pulls
  gigabytes, needs GPU tuning, and small open VLMs underperform on dense
  datasheets. Ollama support already exists for users who want this.
- MCP sampling (`sampling/createMessage`), letting the server call back
  into the harness's model. Elegant, but harness support is sparse,
  it cannot work over the CLI or HTTP surfaces (breaking adapter
  parity), and it hides the cognitive work from the user's transcript.
- Let the agent write gold files directly into the data dir (documented
  file format, no protocol). No validation, no transactionality, no
  resume story, and it couples every harness to the on-disk layout. The
  repo's own no-hacky-workarounds stance argues for extending core +
  adapters instead.
- One-shot handoff: a single `ingest_harness(results_for_all_pages)`
  call. Minimal API, but a 40-page submission is one giant payload,
  there is no resume after compaction, no fan-out, and validation errors
  arrive all at once at the end.
