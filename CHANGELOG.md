# Changelog

All notable changes to Anchor are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Unreleased changes accumulate under `## [Unreleased]` and roll into the
next version section on tag.

## [Unreleased]

### Added

- Live canvas presence (deferred half of #322, part of #321): the canvas
  header now shows who is on this canvas right now. Every SSE subscriber
  to `GET /api/workspaces/{slug}/events` registers itself with an actor
  kind and label (optional `?actor_kind=&actor_label=`, default
  `human`/"browser"; the `/m/:id` monitor view registers as
  `human`/"monitor"), and each join or leave broadcasts a `presence`
  event carrying the full current roster, so clients stay stateless.
  Agents hold no SSE connection, so a write carrying an `agent` actor
  counts as presence too: the author stays on the roster for 90 seconds
  past its last write, marked `via: "writes"`. The same roster reads back
  through `GET /api/workspaces/{slug}/presence`, the `canvas_presence`
  MCP tool (`canvas_advanced` tier), and `anchor canvas presence <slug>`.
  Presence is ephemeral, in-memory state of one `anchor serve` process:
  nothing is persisted, and a second serve sees its own clients only.

- Review states on canvas nodes (closes #324, part 3 of #321): the
  documented convention `data.review = {state: "proposed" | "accepted" |
  "rejected", by?, at?}` gives the human half of the delegation loop an
  object to act on. Opt-in per workspace via `metadata.review_mode`
  (default off — existing flows are untouched), settable through
  `PATCH /api/workspaces/{slug}` (`review_mode`), the
  `canvas_set_review_mode` MCP tool, and `anchor canvas review-mode
  <slug> --on/--off`. With the flag on, nodes created by an `agent` actor
  (#322) are stamped `{state: "proposed", by: <actor>, at}` server-side
  unless the caller supplied its own `review` object. The web UI badges
  proposed nodes and offers one-click Accept / Reject in the selection
  toolbar (a plain update-node patch recording the human in `by`);
  rejected nodes render dimmed with the badge rather than hidden. A
  malformed `review` object on add-node/update-node surfaces the
  standard non-blocking `warning`; the write always succeeds. Backed by
  a new additive `WorkspaceMetadataUpdated` event (deep-merge patch
  semantics, `None` deletes), which older readers skip on replay.

### Fixed

- Cold-boot replay now applies `ReferenceRemoved` and `ReferenceUpdated`
  events: both were missing from the replay type map, so a bibliography
  deletion or caption edit newer than the snapshot was silently dropped
  when state was rebuilt from `events.jsonl`. (#324)

## [0.4.0] - 2026-09-09

### Added

- The intents queue is visible in the web UI (closes #323, part 2 of
  #321): a new Intents tab in the left files explorer lists the project's
  open intents live (SSE `intent_pending` signal plus an 8s polling
  fallback that catches agents resolving over stdio MCP / CLI from other
  processes) with a collapsed "recently resolved" section that shows each
  record's resolution text. The panel authors free-text intents via the
  new additive `user_request` kind — its payload carries the text plus,
  when the user attaches the selected canvas node as the target, the same
  `{workspace_id, node_id}` node-ref shape `drop_to_ingest` uses — and can
  dismiss an open intent (resolve with `{dismissed: true}`). An unread
  badge on the tab counts open intents from any tab, so a canvas file-drop
  in a harness project surfaces immediately. The kind is recognized across
  HTTP / MCP / CLI unchanged (adapter parity via the existing enqueue /
  list / resolve surfaces).

- Every canvas event now records who caused it (closes #322, part 1 of
  #321): the `DomainEvent` envelope gains an additive optional
  `actor: {kind: human|agent|system, id?, label?}` field. Adapters stamp
  defaults — HTTP writes are `human`/"browser" (a request-body `actor`
  overrides), MCP writes are `agent` labeled with the connected client's
  name (falling back to "mcp-agent"), and the CLI is `human`/"cli" unless
  `ANCHOR_AGENT` is set or `anchor canvas --actor kind[:label]` is given.
  System-generated cascades (the `EdgeRemoved` fan-out of a `NodeRemoved`)
  are attributed `system` with causation preserved. Events logged before
  the field existed read back with a null actor and replay unchanged. The
  actor rides the SSE stream; the web UI shows "by <label>" on live
  activity toasts for non-browser actors and an "edited by <label>" chip
  in the properties panel for nodes touched during the session (persisted
  per-node attribution and presence are #325).

- Producer node types resolve through their OIP `renders` token (closes
  #309, spec side OIP#6): the node-types registry folds in every discovered
  manifest's `ui_hints.node_types` entries, so `GET /api/node-types`, MCP
  `canvas_node_types`, and `anchor canvas node-types` describe third-party
  types with an additive `renders` key, and the canvas resolves a node's
  renderer by exact node_type first, then its declared token, then the
  default box (a `graphtracer:chart_series` node now draws with
  `ChartPrimitive`; unrecognised tokens fall through, never error).
- `extensions status` now also lists discovered system/project OIP producers
  (from `~/.config/oip/producers.d/` and `<data-dir>/.oip/producers.d/`) with
  a static resolvability check on each manifest's `invocation.command`
  ("command found on PATH" / "command not found on PATH"), marked
  `started: false` — Anchor never spawns discovered producers; the harness
  does. Adapter parity via the shared payload builder: the
  `anchor_extension_status` MCP tool and `GET /api/extensions/status` serve
  the same `producers` section. (#308)
- `canvas add-node` / `update-node` / `add-edge` / `update-edge` `--data`
  accepts `@path` to a JSON file, with the same semantics as
  `derive-region --region`; the `@` handling is one shared CLI helper now
  used by `derive-region` and `resolve-ref` too. (#288)
- Spec-row enrichment records the matched table cell (#242 P2c, closes
  #274): when a row's value matches one gold cell, the row's `source_ref`
  gains a `cell: {row, col}` selector alongside the cached cell bbox, and
  the web viewer resolves selector-bearing refs through
  `GET /api/documents/{slug}/resolve-ref` so the click-to-source highlight
  lands on the referenced cell instead of the whole table region. Refs
  without selectors keep the unchanged region-level highlight path.
- `remove-region`: the cleanup half of `derive_region`, with adapter parity —
  MCP `remove_region`, HTTP `DELETE /api/documents/{slug}/regions/{region_id}`,
  CLI `anchor remove-region`. Only regions carrying `derived_from` are
  deletable (model-extracted gold is refused with a structured error), and
  the region's vector is dropped from `embeddings.json` so search stays
  consistent. (#304)
- `canvas add-node` / `add-edge` responses surface the created `node_id` /
  `edge_id` at top level on all three adapters (CLI JSON, MCP result, HTTP
  response) — additive keys; the `event`/`state`/`position` envelope is
  unchanged. (#307)

### Fixed

- `derive_region` parent lookup is no longer page-ambiguous: region ids are
  only unique per page, so `parent_region_id` accepts the `p4/r1` token form
  `inspect_region` uses, an explicit page wins, and a bare id matching
  regions on multiple pages fails with a structured error listing the
  candidate pages (MCP `candidate_pages`, HTTP 409) instead of silently
  binding the first match. Bare ids with a single match keep working. (#287)
- `derive_region` mints the next free `r<n>` id on the target page when the
  producer omits one, so a stored region is always addressable; explicit
  producer ids pass through untouched. (#304)
- `anchor canvas` mutation commands (`add-edge`, `add-node`, `update-node`,
  `update-edge`, `remove-node`, `remove-edge`, `state`, `clear`,
  `placeholders`) print a one-line structured message to stderr and exit 1
  on domain errors (unknown node/edge id, unknown workspace) instead of
  crashing with a Rich traceback. (#305)

- `anchor check` now leads with the project the current directory actually
  resolves to — the same cwd `anchor.toml` walk every other command uses —
  naming the project, where its name came from (marker path, `--project`,
  `ANCHOR_PROJECT`, `anchor use`, or the env default), its data dir, and the
  serve bound to *that* project's data dir. A new `--project` flag joins
  `--env`; both override the cwd marker. Previously check always reported the
  env default project, so "Ready ✓" could describe a different data dir than
  the one an `ingest` from that folder would use. (#303)
- `anchor canvas snapshot` resolves its default `--base-url` through the
  serve registry (the lookup `anchor canvas url` uses), so a serve on a
  bumped or per-project port is found instead of a guessed `:8002`; an
  explicit `--base-url` still overrides, and a missing serve is warned about.
  The headless snapshotter also waits for at least one rendered node when
  the workspace state says nodes exist, and times out with an error naming
  what it waited for — no more silent empty-grid PNGs. (#306)
- Skill/help drift: the core skill no longer claims gold extraction requires
  `ANCHOR_OPENAI_API_KEY` unconditionally (a plain `OPENAI_API_KEY` is
  accepted for the `openai` provider; `local`/`ollama`/`harness` need no
  key), and `anchor embed --help` states the environment's configured
  `embed_model` is used — local bge is only the local-provider default — and
  that search skips documents whose stored embed_model mismatches. (#302)

- MCP per-workspace write locks moved to a process-level registry keyed by
  (project data dir, workspace slug), so evicting a project's runtime bundle
  from the router's size-8 LRU and re-resolving it hands writers the same
  lock objects, so bundle eviction can no longer defeat write serialization.
  Also stops allocating a throwaway `asyncio.Lock` on every lock-map hit.
  (#272)
- `anchor check` completes on Windows terminals using the default cp1252
  console encoding instead of raising `UnicodeEncodeError`: the
  harness-provider status line is plain ASCII (`begin -> submit pages ->
  finalize`), and when stdout cannot encode the report's glyphs the check
  marks / arrows degrade to ASCII markers (`OK`, `->`) with anything else
  replaced rather than crashing. (#267)

### Security

- A `local_only` environment can no longer send document text to a remote
  embedding endpoint (#271): `build_embedder` refuses at construction time to
  build the remote OpenAI embedding client without an explicit,
  policy-approved credential. Previously a `text-embedding-*` `embed_model`
  in a no-egress environment built a client that fell back to the ambient
  `OPENAI_API_KEY`. The egress-policy refusal now names the `embed_model`
  setting and the local fix, and `anchor check` reports the contradiction as
  a clean "Not ready" with exit code 1 instead of printing "local-only : ON"
  next to a remote embed model (or crashing with a traceback).
- Web routing moved to react-router 7 (react-router-dom `^7.18.0`,
  resolving react-router 7.18.3), clearing both open advisories against
  the 6.x line — GHSA-337j-9hxr-rhxg (constructor injection via SSR error
  deserialization) and GHSA-wrjc-x8rr-h8h6 (open redirect via backslash
  in `Link`/`useNavigate`) — which are patched only in 7.18.0. Declarative
  `BrowserRouter`/`Routes` usage is unchanged, so the three routes (`/`,
  `/c/:id`, `/m/:id`) behave identically, including the read-only monitor
  view. (#316)

## [0.3.0] - 2026-09-08

Everything since v0.2.5: the v0.2.6–v0.2.8 tags shipped without rolling
the changelog, so their contents are part of this section.

### Added

- Gold region crops are rendered lazily on first read at the canonical
  `gold/<slug>/pages/<page>/<region_id>.png` path (300 dpi default, `--dpi`
  up to 600), fixing every already-ingested document retroactively — the
  crop contract the skill and the OIP `consumes` handoff promised but the
  pipeline never wrote. `anchor page-image` (and its HTTP/MCP peers) gained
  a `dpi` option that renders from the bronze PDF and caches the variant.
  Parity across `anchor crop` / MCP `get_crop` / HTTP `/crops/{rel_path}`,
  with tolerant region addressing (`4/r1.png`, `p4/r1`, bare `r1`) and
  errors that say whether the region exists and where. (#310)
- `source_ref` can point below the region (#242 P2): optional `item_id`
  (one silver item, `p<page>-i<n>`) and `cell` (`{row, col}`) selectors,
  resolved by the new `resolve_source_ref` with precedence
  cell > item > region > bbox and a `precision` field naming the layer
  that answered. Legacy refs resolve byte-identically. MCP
  `resolve_source_ref`, HTTP `GET /api/documents/{slug}/resolve-ref`,
  CLI `anchor resolve-ref`. (#311)
- `inspect_region` / `get_region_content` return a region's stored
  provenance: `derived_from`, the stored (parent) `source_ref`, the
  producer payload as `data`, and — on inspect — `members`, the silver
  items behind `member_item_ids` with their bboxes. `derive_region`
  synthesizes the parent's ref when the parent stores none, and mints
  provenance for ordinary gold parents. (#301)
- Gold coverage invariant (#242 P1): every meaningful silver item belongs
  to at least one searchable gold chunk, with an embedding fallback that
  renders reconstructed cell content when a region has no model
  description (fixes caption-less tables being invisible to search,
  #231). Region read-ops `inspect_region` / `get_region_content` landed
  on all three adapters, plus the checked operation-descriptor parity
  table. (#280)
- Preview-style document viewer and left files explorer redesign (#220):
  Files / Canvases / References tabs, drag-to-canvas, continuous PDF
  viewing. (#268)

### Changed

- Bounding boxes are standardized on top-left-origin PDF points across
  silver, gold, and canvas refs, with an automatic migration for stored
  bottom-left data (`anchor migrate bbox-origin`; a running serve
  migrates on start). (#281, #282)
- Extension services are wired through a shared project-runtime module so
  MCP, HTTP, and CLI construct identical per-project bundles. (#270)

### Fixed

- Three MCP/HTTP adapter parity breaks: `GET /api/fmu/simulations` was
  shadowed by the `/{slug}` route and unreachable; `sysml.render` /
  `sysml.export` legacy aliases never routed; the `sysml` capability
  could never activate (it now activates when a canvas holds `sysml:*`
  nodes). Also contained the FMU store's `get_model` / `get_series` read
  paths against traversal ids. (#300)
- MCP Python SDK pinned to v1-compatible imports and the fitz "Loading
  weights" progress noise kept off stdout, so CLI JSON output and MCP
  stdio framing stay clean. (#259, #261)

### Added

- Canvas References panel, docked on the LEFT with the PDF source pane (slice 3
  of #147):
  - With the source dock open, the left region lists the canvas bibliography.
    Each row shows the label (or a quote / slug+page fallback), the source doc
    slug and page, a short quote snippet, and a crop thumbnail when the
    reference has a bbox.
  - Click a reference to open its source in the dock at its page with the bbox
    (and quote) highlighted, reusing the deep-zoom viewer.
  - Rename a reference's label or delete it from the panel.
  - The panel live-updates: a reference made via "Make reference" in the dock
    appears immediately (the references API emits an `anchor:references-changed`
    browser event the panel refetches on).
- Reference remove / update (label) ops, with MCP / HTTP / CLI parity (slice 3
  of #147): drop a reference from the bibliography or edit its caption. Only the
  label is mutable; the `source_ref` locator is immutable. HTTP
  `DELETE /api/workspaces/{slug}/references/{id}` and
  `PATCH /api/workspaces/{slug}/references/{id}`; MCP `canvas_remove_reference` /
  `canvas_update_reference`; CLI `anchor canvas reference remove|update`. Both
  emit `ReferenceRemoved` / `ReferenceUpdated` domain events so SSE clients
  update; an unknown reference id errors.
- Canvas references store, with MCP / HTTP / CLI parity (slice 1 of #147):
  - A per-canvas bibliography lives in canvas meta as `references` (a list of
    `{id, label?, source_ref, created_by, created_at}`). `source_ref` is a
    `{slug, page, bbox?, region_id?, detail?}` locator that mirrors the per-row
    source_ref spec nodes already carry, so a reference can drive the existing
    value-level highlight once attached.
  - Three ops reach all three adapters: create a reference, list the
    bibliography, and attach a reference to a node (or one spec row by index).
    Attaching sets the target's `reference_id` pointer plus its `source_ref`.
    HTTP `POST/GET /api/workspaces/{slug}/references` and
    `POST /api/workspaces/{slug}/references/{id}/attach`; MCP
    `canvas_create_reference` / `canvas_list_references` /
    `canvas_attach_reference`; CLI `anchor canvas reference create|list|attach`.
  - Backward compatible: a canvas with no `references` key behaves exactly as
    before. References survive a cold-boot replay from the event log.
  - Scope is canvas-level for now; the shape and op signatures are written so
    the store can move to project level later for cross-canvas reuse / paper
    compilation.

### Changed

- Canvas node-write API hardening, with MCP / HTTP / CLI parity:
  - `update-node` / `update-edge` now deep-MERGE the given `data` into the
    node's existing data instead of replacing it. Unmentioned keys (e.g. a
    node's `source_ref`) survive; nested dicts merge; a key set to `null` is
    deleted (#192).
  - The write surfaces accept `type` as an alias for the canonical
    `node_type` / `edge_type`, so a record read from canvas state can be
    written straight back (#186).
  - `add-node` with no `x`/`y` (or `place="auto"`) auto-places a
    non-overlapping position server-side and returns it under `position`;
    explicit coordinates still land exactly (#189).
- The per-node-type data-field contract is now explicit and queryable:
  `anchor canvas node-types`, `GET /api/node-types`, and the
  `canvas_node_types` MCP tool return which `data` keys each built-in node
  type renders and which is its body field. `add-node` / `update-node`
  attach a non-blocking `warning` when given a `data` key the type does not
  render (e.g. `data.body` on a `fact`, which renders `data.text`) (#191).

- URL assertions in `test_openai_client_zone.py` now compare the parsed
  hostname (via `urlsplit`) instead of substring checks, clearing three
  `py/incomplete-url-substring-sanitization` CodeQL alerts (#165).
- `_QUIETED` bool + `global` reassignment replaced with a `_STATE` dict in
  `quiet.py` and `docling_extractor.py`, clearing two
  `py/unused-global-variable` CodeQL alerts (#165).

### Added

- Server self-identification (#177, #179): a running `anchor serve` now records
  its actual binding (env, project, data dir, host:port) so a client can tell
  which project a port hosts instead of assuming `:8002`. Surfaced with parity
  across all three adapters: HTTP `GET /api/whoami`, the MCP `server_info` tool
  (advertised by default), and the `anchor serve-info` CLI command (lists
  running serves, or prints one project's base URL with `--project`). `anchor
  check` now reports whether a serve is bound to this project. `anchor canvas
  url` resolves against the serve actually serving this project's data dir, so
  the printed port is the real one (fixing the hardcoded `:8002` that pointed at
  the wrong project when the port was taken); it warns when no serve is running.
- Pointed extraction (#132): pull a selected set of gold regions / entities out
  of a document into a caller-defined JSON shape, with every filled leaf
  grounded to its source cell. `select` is any of `{regions, pages, entity}`
  (entity reuses synopsis scoping); `shape` is by-example or a JSON Schema. The
  response is `{doc_slug, data, provenance (JSON-Pointer -> source_ref
  {page, region_id, bbox, quote}), unfilled}` -- filled leaves carry provenance,
  unfillable leaves are listed in `unfilled` and never guessed. Parity across
  MCP (`extract_pointed`, in the core tool set), CLI (`anchor extract <slug>
  --shape shape.json [-o out.json]`), and HTTP
  (`POST /api/documents/{slug}/extract`).
- Agent intent/request queue (#148): a durable, project-level queue of user
  canvas actions for a harness to act on, surfaced without the event firehose.
  Push-notify / pull-payload transport (a lightweight `intent_pending {count}`
  SSE signal on the event bus; pull the payload via `list_pending_intents`).
  Drop-to-ingest in a harness-ingest project now enqueues a `drop_to_ingest`
  intent and marks the node "awaiting agent"; `make_reference` /
  `attach_to_fact` are recognized kinds the queue stores (authoring is #147).
  Parity across HTTP (`/api/intents` + `/events`), MCP (`list_pending_intents`,
  `next_intent`, `resolve_intent`, in the core tool set), and CLI
  (`anchor intents`, `anchor intent resolve`).
- Local-only / no-egress ingest mode for confidential documents (#48). The
  `local` provider now records `local_only = true`, and the runtime asserts it
  identically across CLI, HTTP and MCP: ingest + embed build no OpenAI client
  for any stage regardless of key presence, and HuggingFace model loading is
  pinned offline (`HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`) so cached weights
  load without reaching the network.
- `anchor models prefetch` (+ `anchor models list`) to download the local model
  set (bge-small embedder + docling layout/OCR) ahead of time, so a later
  offline run works. CLI-only: a one-time provisioning command, not on the
  per-call ingest path.
- `anchor check` now echoes the local-only posture and the offline model set;
  the runtime status payload carries a `provider.local_only` flag.

### Changed

- MCP server now advertises a tiered tool surface. A small core (~15 tools:
  ingest/list/read/search documents, the common canvas verbs, project
  list/create) is advertised by default; the long tail (FMU, CAD, SysML, the
  harness ingest sub-protocol, advanced canvas and document ops) is gated.
  Gated tools stay callable by name and are discoverable via the new
  `anchor_list_capabilities` meta-tool; an extension's tools auto-appear in
  the default list once the open project has data for it. This keeps a base
  PDF+canvas project from drowning tool-search in large-surface harnesses
  (down from ~48 advertised tools). (#133)

## [0.2.5] - 2026-06-17

Grounding, harness ingest, and agent onboarding release. This is the wheel to
publish after the recent canvas provenance, gold-ingest, and `anchor init`
follow-up fixes.

### Added

- Harness-driven PDF ingestion across MCP, HTTP, and CLI. This lets an agent
  run the staged gold-ingest workflow without storing a project API key in
  ANCHOR itself, while still publishing a complete gold layer atomically.
- A `harness` provider option in `anchor init` for projects where the agent
  performs the vision extraction.
- In-repo Claude Code plugin metadata so ANCHOR can be installed through the
  Claude Code plugin flow as well as by `anchor install claude-code`.
- AX report issue templates and agent guidance for filing usability findings
  as GitHub issues instead of leaving them in local notes.

### Changed

- Table-cell provenance is preserved through the silver and gold layers when
  Docling provides cell coordinates, so row source buttons can point at the
  selected value rather than only the enclosing table region.
- Gold ingest now uses a transactional staging substrate with a completeness
  marker and shared region validation before publishing.
- `anchor check` reports the resolved data dir more clearly, including the
  case where the directory does not exist yet.
- The MCP harness skill now triggers ingestion from user intent, not only from
  provider configuration.

### Fixed

- Restored row-level source buttons on populated spec tables after the
  row-provenance guidance regressed to node-level references.
- External canvas events now stream live to connected clients.
- `anchor install claude-code` writes the MCP registration to the Claude Code
  config file that Claude Code actually reads.
- Harness ingest begin now accepts a multipart upload over HTTP instead of a
  local filesystem path.
- Unknown ingest-session errors now include a clearer diagnostic and the
  session work order includes the resolved data dir.
- Invalid region and cell bboxes are rejected instead of being drawn on the
  wrong part of the page.
- The local `sentence-transformers` embedder now starts loading its model when
  the embedder is constructed, so the first `search_documents` call after a
  server restart is less likely to hit an MCP client timeout.

### Security

- The web lockfile now pins a patched `protobufjs` through the pnpm override
  used by the frontend supply-chain audit.

## [0.2.4] - 2026-06-11

Config robustness for cross-platform onboarding. Two fixes that stopped a
project's `anchor.toml` from being honored, both found while testing a fresh
setup (one on Windows).

### Fixed

- `data_dir` with a leading `~` (in `anchor.toml`, `ANCHOR_DATA_DIR`, or
  `--data-dir`) was taken literally, creating a `./~` folder inside the project
  and reading from the wrong place. It now expands `~` and `$VAR` from every
  config source.
- On Windows, `anchor init` wrote `anchor.toml` in the default locale encoding
  (cp1252), so a non-ASCII character became a byte the UTF-8 reader rejected and
  the whole config was silently dropped in favor of the global data dir. The
  writer now forces UTF-8 (and keeps the template ASCII); the reader decodes
  `utf-8-sig` then falls back to cp1252, so an already-corrupted file still
  loads. No re-`init` needed after upgrading.

## [0.2.3] - 2026-06-09

Azure-onboarding hardening. Found by walking a fresh-folder Azure test-drive end
to end: a self-correcting `anchor init`, a `anchor check` preflight, and a fix
for a data-egress edge case.

### Added

- `anchor check`: verify the resolved data zone before ingesting. Prints the
  provider, endpoint, data dir, models, and whether the key is present; repairs
  a malformed Azure endpoint (`--fix`); and with `--probe` makes one tiny call
  (no document content) to confirm the deployment resolves and the key
  authenticates. Exits non-zero when something would break a real ingest.
- An Azure OpenAI test-drive guide, led by a "create & verify your deployment"
  prerequisite, plus a "set up a project" section in the agent skill so an agent
  can scaffold ANCHOR non-interactively (`anchor init --yes --provider …`).
- `anchor --version` flag (alias of `anchor version`) and `anchor canvas url
  <slug>`, which prints the deep link `http://<host>:<port>/c/<slug>`; `anchor
  canvas create` now also prints that URL. Surfaced by an agent-experience test
  session that otherwise had to reverse-engineer the canvas route.

### Changed

- `anchor init` self-corrects an Azure endpoint that is missing `/openai/v1/`
  (the common bare-resource-URL paste), and offers to save the API key to a
  gitignored `.env` (never the committed `anchor.toml`). The readback now
  reports key state honestly and warns when only a personal `OPENAI_API_KEY` is
  present for a named (Azure/custom) endpoint, where it is the wrong credential.

### Fixed

- **Data-boundary leak:** the OpenAI clients now always honor the configured
  `base_url`. Previously, a missing `ANCHOR_OPENAI_API_KEY` built a bare
  `OpenAI()` that dropped the endpoint and sent document pages to public
  `api.openai.com` (using any `OPENAI_API_KEY` in the environment) instead of
  the Azure/custom endpoint the user configured.
- `anchor version` now reports the installed distribution version. It was
  hardcoded and read `0.2.0` through the 0.2.1 and 0.2.2 releases.
- `anchor ingest` is now idempotent, matching its documented contract: if the
  slug already has gold it returns `{skipped: true}` instead of silently
  re-running the billed bronze→silver→gold→embed pipeline and overwriting the
  gold. Pass `--force` (MCP/HTTP `force`) to recompute. Surfaced by an
  agent-experience test that re-ingested a document and got an unexpected ~190s
  Azure recompute.
- HuggingFace and docling no longer leak progress bars and log chatter (the
  "Loading weights" bar, the "unauthenticated requests to the HF Hub" notice,
  RapidOCR INFO lines) into the output of `anchor search` / `embed` / `ingest`.
  Dependency logging is quieted once at startup, leaving `stdout` pure;
  `ANCHOR_LOG_LEVEL=DEBUG` restores the full stream.

## [0.2.2] - 2026-06-09

Onboarding and configuration release. A folder is now a project, configured once
with `anchor init`, and usable by any agent without a per-project reinstall.

### Added

- `anchor init`: an interactive command that configures a project folder. It
  asks where document content may go — the **AI provider**, which is also the
  **data zone** (`local`, `ollama`, `openai`, `azure`, or any OpenAI-compatible
  `custom` endpoint) — then picks the embedding model and data directory and
  writes a non-secret `anchor.toml`. The API key is never written to the toml.
- Project configuration via `anchor.toml`, discovered by walking up from the
  working directory or via `ANCHOR_CONFIG`. The CLI, server, and `anchor-mcp`
  all resolve the same project.
- `anchor-mcp --project <folder>` to target a project explicitly.
- Arrow-key provider and embedding-model pickers in `anchor init`.
- Documentation: a Projects concept page, an Azure OpenAI recipe, and the
  folder-as-project model across getting-started, guides, and reference pages.

### Changed

- `anchor install <harness>` registers a folder-resolving MCP entry by default
  (no baked `--data-dir`): one registration serves every project, with no
  reinstall when switching. Pass `--data-dir` to pin a single project.
- The `docling` accelerator defaults to `auto`: CUDA when present, otherwise
  CPU, automatically avoiding the Apple-Silicon MPS float64 crash.
- `anchor serve` falls through to the next free port when the requested one is
  taken, and prints the chosen URL.

### Fixed

- Azure OpenAI works through its OpenAI-compatible v1 endpoint; `anchor init`
  no longer flags the provider as unavailable.
- Gold region extraction retries without JSON mode when an endpoint (some Azure
  deployments, some local servers) rejects `response_format`.
- A malformed `anchor.toml` is ignored with a warning instead of crashing the
  CLI, and `anchor init` replaces an unreadable config without `--force`.

## [0.2.1] - 2026-06-08

Patch release for the first public testing round after `v0.2.0`.

### Added

- MkDocs documentation site, including installation, document/canvas workflow,
  MCP client configuration, citation, and architecture pages.
- Public release notes page explaining the difference between `0.2.0` and
  `0.2.1`.
- Source checkout install guidance for testers when the published PyPI wheel is
  behind `main`.
- Gemini CLI MCP configuration example.
- Canvas ingestion progress feedback and per-document timing reports under the
  silver document folder.
- Canvas workspace deletion from the web workspace list.
- Diagnostics for embedding model mismatches during document search.

### Changed

- Documentation and public metadata now use the ANCHOR expansion
  "Agent-Native Canvas to Help Organize Resources".
- CLI entrypoint split into smaller command modules for maintainability.
- `ANCHOR_DATA_DIR` is honoured consistently by CLI defaults.
- Docling dependency updated to 2.94.0 and Vitest updated to 4.1.0.
- Security policy, contribution notes, and agent setup guidance tightened for
  public repository use.

### Fixed

- Windows PDF ingest now writes text and JSON artifacts as UTF-8, avoiding
  `charmap` failures when extracted PDF text contains Unicode characters.
- Document node region overlays and source links render correctly when region
  bbox data arrives in either supported shape.
- Region extraction now exposes a normalized `bbox` for approximate regions.
- Upload and ingest progress states are visible on the canvas while document
  processing is running.
- CodeQL alerts from the first public scan were addressed.
- Static documentation diagrams and branding assets render without Mermaid
  syntax failures.

## [0.2.0] - 2026-05-25

First public release. The v2 hexagonal-modular-monolith codebase moved
from `v2/` to the repo root, the legacy v1 stack (Next.js +
CopilotKit + FastAPI + pgvector) was archived on the `archive/pre-v2`
branch, and a focused OSS readiness pass landed every "real blocker"
flagged by the pre-release review.

### Added

- MIT license + reflected in package metadata.
- `safe_upload_name()` / `assert_within()` path-containment helpers
  applied at every upload route (PDF, FMU, CAD) and re-applied
  defensively inside the filesystem stores.
- `validate_workspace_slug()` policy applied at HTTP, MCP, CLI, and
  filesystem boundaries; surfaced as a clean HTTP 400 instead of a 500.
- `FmuRuntime.synthetic` flag propagated onto `FmuModel`,
  `SimulationRun`, and `TimeSeries` so consumers can render a
  `[SYNTHETIC]` badge.
- `ANCHOR_FMU_DEMO=1` env var as the explicit opt-in for the offline
  synthetic FMU runtime.
- `ANCHOR_CORS_ORIGINS` env var for additional CORS origins beyond the
  bundled Vite dev origins.
- `PATCH /api/workspaces/{slug}` to rename a workspace's display title;
  sub-canvas tiles cascade the rename to the child workspace's
  `meta.title`.
- `web/eslint.config.js` (flat config for ESLint 9).
- `.env.example` covering every documented `ANCHOR_*` variable.
- This `CHANGELOG.md` and the `.github/workflows/release.yml` tag-driven
  publication pipeline.

### Changed

- PyPI distribution name: **`anchor-kb`** (the Python import path stays
  `anchor`; only the wheel/sdist filename and `uv tool install`
  invocation pick up the `-kb` suffix).
- Default HTTP bind: `0.0.0.0` → `127.0.0.1`. Pass `--host 0.0.0.0`
  or set `ANCHOR_HTTP_HOST=0.0.0.0` for LAN exposure (you are then
  responsible for adding auth via a reverse proxy).
- CORS: wildcard `*` → exactly the dev Vite origins, plus the
  `ANCHOR_CORS_ORIGINS` opt-in.
- FMU runtime resolution: silent fallback to `FakeFmuRuntime` is
  replaced by a fail-closed `FmuRuntimeUnavailableError`. The previous
  behaviour could return synthetic sinusoids that looked like real
  simulation output, which is unsafe for an engineering tool.
- `FsDocStore.get_crop_path()` now resolves the candidate and asserts
  it stays under the document's gold-pages root, replacing an ad-hoc
  `re.sub(r"\.\.+", ".", …)` substitution that did not handle Windows
  separators or absolute paths.
- README install: `uv sync` → `uv sync --extra dev`; `pnpm --filter`
  → `pnpm --dir web`; updated test counts and added a Limitations
  section + a Security model section.

### Removed

- 17 draft architecture diagram iterations (`-v1` through `-v16`,
  `-v18`, `-v19`) plus four unused sibling assets. Kept the canonical
  `architecture-diagram-v17.png`, `ingestion-pipeline-v3.png`,
  `oip-extension-anatomy-v2.png`, and `sysml-ir-round-trip.png`.
  `docs/assets/` dropped from 75 MB to 14 MB.
- 22 tracked `.playwright-cli/*.yml` session artefacts that lived
  under a `.gitignore`d directory.
- The 210-line in-tree OIP draft spec; replaced with a 26-line pointer
  to the canonical repo at <https://github.com/Novia-RDI-Seafaring/OIP>.

### Security

- Unauthenticated HTTP server now binds loopback-only by default.
- Workspace slugs and upload filenames go through a documented
  identifier policy at every public boundary.
- Snapshot output paths and the SPA static catch-all both apply
  resolve-and-contain checks.

[Unreleased]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.5...HEAD
[0.2.5]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Novia-RDI-Seafaring/anchor/releases/tag/v0.2.0
