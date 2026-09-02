# Architecture

## Thesis

ANCHOR is a **canvas primitive** with **swappable extensions**. The
canvas is a small, domain-agnostic piece of software that knows about
nodes, edges, workspaces, and events. Everything that turns a PDF into
something you can drag onto that canvas — Docling extraction, vision-LM
region detection, region cropping, FMU inspection — lives in an
**extension**, sits behind a stable contract, and can be replaced
without touching the canvas.

The contract has a name: the **Open Ingestion Protocol** (OIP). It's
versioned separately and lives in its own
[repository](https://github.com/Novia-RDI-Seafaring/OIP).

A canvas with no extensions is empty but functional. A canvas with two
extensions (PDFs, FMUs) is what we ship today. A canvas with someone
else's extension (audio transcripts, code regions, video frames) is
why OIP exists.

The runtime, durable stores, event bus, consumers, and ports-and-adapters
layers are shown together in [The hexagon](#the-hexagon).

---

## Runtime composition

Each project is wired through `ProjectRuntime`, the shared composition
root for one resolved project config and data directory. It owns the
service instances that adapters should share: workspace service,
document store, event bus, ingest services, agent intents, and optional
extension services.

HTTP, MCP, and CLI entry points ask for that runtime instead of each
building their own copies. This keeps adapter behaviour aligned: a
canvas mutation, PDF ingest, search, or intent operation reaches the
same stores and event bus no matter which interface started it. Tests
can still pass explicit services to the HTTP app when they need a small
isolated runtime.

Callers select a named profile: `canvas`, `ingest`, `extensions`,
or `full`. Long-running HTTP and MCP processes use the full profile.
Short-lived CLI commands request the smallest profile that supports
their operation. Listing or moving canvas nodes therefore does not load
Docling or an embedding model. Commands that require an omitted service
fail with an error that names the active profile.

Each runtime gives `WorkspaceService` an
`InProcessWorkspaceLocks` adapter. Mutations to one workspace are
serialized across concurrent requests for the complete load, validate,
append, snapshot, and publish sequence. Different workspaces can still
progress independently. These locks do not coordinate separate
operating-system processes, so one server process must remain the
authoritative writer for a shared data directory.

### Environment egress boundary

The environment, not the project or canvas, owns model egress. Its provider,
endpoint, and local-only setting form one trust policy shared by every project
in that environment. A project may keep its own corpus and canvas state, but it
cannot redirect the endpoint or weaken local-only mode. Process configuration
cannot silently retarget a named environment either. Use a second environment
and a second named MCP server when a corpus needs a different trust policy.

Runtime composition resolves one `EgressPolicy` before constructing model
clients. The `local` and `harness` providers construct no Anchor-side remote
model client, and a remote embedding model is rejected for either provider.
Public OpenAI may deliberately use `OPENAI_API_KEY`; Azure and custom endpoints
require an explicit environment-scoped `ANCHOR_OPENAI_API_KEY`. The low-level
client factory never reads ambient credentials. Each environment's gitignored
`.env` is parsed into that environment's config without mutating process-global
state, so resolving one environment cannot leave its key active in another.

`harness` means no Anchor-side model endpoint, not no document disclosure. In
harness-driven ingest, the connected agent reads page work items and submits
results. Its model provider and retention policy are outside Anchor. Classified
or otherwise restricted documents require the `local` provider and must not be
given to a cloud-backed harness.

---

## The three substrates

| Substrate     | Lifetime                | Where it lives             | Owned by             |
| ------------- | ----------------------- | -------------------------- | -------------------- |
| **Documents** | durable, shared         | `data/<producer>/...`      | producer extensions  |
| **Canvases**  | durable, per-workspace  | `data/canvases/<slug>/`    | canvas core          |
| **Session**   | ephemeral, per-process  | in-memory event bus        | canvas core          |

Documents and canvases are **independent**. The same PDF can appear on
many canvases; deleting a canvas doesn't delete the PDF; a fresh
clone of `data/` on another machine yields the same canvases and the
same documents because everything is plain files.

The session substrate is the live wire — every mutation publishes a
`DomainEvent`, and the HTTP, MCP, and SSE adapters all subscribe to it.
That's how a node-move in one browser tab shows up in a second tab and
in an agent's MCP view within ~50ms, with no separate sync layer.

---

## The hexagon

ANCHOR's Python package follows ports-and-adapters layering, enforced
in CI by `import-linter`. The contracts (verbatim from `.importlinter`):

```
adapters → infra → core              (one direction only)

core MUST NOT import:                fastapi, openai, mcp, pymupdf,
                                     docling, uvicorn, starlette,
                                     typer, aiofiles, sse_starlette

infra MUST NOT import:               fastapi, mcp, uvicorn, starlette,
                                     typer, sse_starlette

core, infra MUST NOT import:         anchor.extensions.*
```

In English: **the canvas core is pure**. It knows the shape of a
workspace and how to apply an event to one; it cannot open a file, hit
a URL, or call an LLM. Concrete I/O lives in `infra/`. Transport — HTTP
routes, MCP tool definitions, CLI subcommands — lives in `adapters/`.
Anything PDF- or FMU-specific lives in `extensions/` and the canvas
itself does not import it.

![ANCHOR runtime and hexagonal architecture](../assets/diagrams/hexagon-architecture.svg)

*The runtime separates source producers, durable document and canvas
stores, ports-and-adapters layers, and consumers. The core is pure
domain; `.importlinter` fails the build if code reaches across a
boundary or pulls a transport or vendor SDK into a place it does not
belong.*

### What lives in each layer

| Layer        | Path                              | Examples |
| ------------ | --------------------------------- | -------- |
| `core`       | `src/anchor/core/`                | `Workspace`, `DomainEvent`, `WorkspaceService`, port protocols |
| `infra`      | `src/anchor/infra/`               | `MemoryEventBus`, `FsWorkspaceStore`, `MemoryWorkspaceStore` |
| `adapters`   | `src/anchor/adapters/`            | FastAPI routers, MCP tool handlers, Typer CLI |
| `extensions` | `src/anchor/extensions/anchor_*/` | PDF medallion pipeline, FMU inspector |

Extensions repeat the same shape inside their own boundary — every
extension has its own `core/`, `infra/`, and (optionally) `adapters/`.
The fifth import-linter contract enforces this for `anchor_pdfs`.

---

## Two services

The whole canvas behaviour fits into one service plus extensions can
add their own. Today there are two:

- **`WorkspaceService`** *(core)* — the only thing allowed to mutate a
  workspace. Validates a command against current state, applies the
  event reducer, persists, publishes. Methods: `add_node`, `move_node`,
  `update_node`, `remove_node` (cascades to edges), `add_edge`,
  `remove_edge`, `clear`, `create_workspace`, `list_workspaces`,
  `get_state`. ~13 public methods, every one of them async, every one
  of them returning the new state plus the event(s) that produced it.

- **`IngestService`** *(extension: anchor_pdfs)* — runs a PDF through
  bronze (raw) → silver (Docling extraction) → gold (VLM-polished
  markdown + region detection). Emits progress events on the same bus.

`anchor_fmus` has its own `FmuService` (`upload_and_inspect`,
`simulate`, `list_simulations`, ...). ANCHOR's canvas core never
imports either.

### Region retrieval

PDF ingest writes bronze, silver, and gold artifacts. Silver is the
Docling view: page markdown, item metadata, bboxes, and table cells.
Gold is the agent-facing view: source regions with page, bbox, title,
description, tags, optional cells, and server-derived `content`.

That `content` is rendered by ANCHOR from the Docling items or table
cells selected by the region geometry. It is not submitted by the
agent. Harness ingestion can select a logical sub-table with
`table_slice {candidate_id, rows, columns?}`. ANCHOR persists only those
cells and computes their bbox union, so adjacent tables no longer share one
coarse region. Search embeds region title, description, and content. In
normal use an agent should search gold regions and call `get_gold_regions`
for the matching region. Loading the whole page markdown remains a fallback
for ambiguous or missing region content.

---

## Four ways to talk to it

| Protocol        | Use case                  | Entry point                    |
| --------------- | ------------------------- | ------------------------------ |
| **HTTP REST**   | the React web UI          | `GET/POST /api/workspaces/...` |
| **SSE**         | live updates to clients   | `GET /api/workspaces/{slug}/events` |
| **MCP (stdio)** | agents (Claude, Cursor)   | `anchor-mcp` binary            |
| **CLI**         | scripts, headless ingest  | `anchor` binary                |

All four end up calling the same `WorkspaceService` methods. There is
no second copy of the business logic. An agent moving a node and a
human dragging a node go through the same code path, hit the same
event log, and notify the same SSE subscribers.

The MCP server hosts both canvas tools (`canvas_get_state`,
`canvas_add_node`, ...) and extension tools for PDFs, FMUs, CAD and
SysML. Extension tool names use safe prefixes such as `ingest_pdf`,
`fmu_simulate` and `sysml_render` so they can coexist with other tools
and pass MCP client name validation.

Extension discovery lives in the `anchor.adapters.extension_host`
module. It reads bundled extension manifests and exposes the public
extension list and skill metadata without making adapters know each
extension's filesystem layout. Discovery is separate from runtime
wiring: a manifest says what the extension offers, while service
builders wire the concrete stores, clients, and optional runtimes.

---

## What ships in v2

- **Python package** `anchor` — one wheel, three binaries: `anchor`
  (CLI), `anchor-mcp` (stdio MCP server), `python -m anchor` (module
  entry).
- **React frontend** in `web/` — Vite + React 19 + Tailwind v4 +
  ReactFlow + Zustand + TanStack Query. Compiled into the same wheel
  via `web/dist/`. Same-origin in production, no separate API server.
- **Two extensions in-tree** — `anchor_pdfs`, `anchor_fmus`. Both ship
  OIP manifests. Both are reachable through the same MCP server.
- **Hexagonal layering enforced in CI** — `uv run lint-imports` passes
  five contracts on every push.

---

## What's intentionally not here

- **No auth.** Single-tenant, runs on your laptop. Multi-tenant is on
  the roadmap (see memory note `project_multitenancy_roadmap`).
- **No managed service.** No DB. No Redis. No queue. The substrate is
  the filesystem; the bus is in-process. Two browser tabs sync via SSE
  on a single Python process.
- **No vendor SDK in the canvas.** OpenAI imports live in
  `anchor_pdfs.infra.llm`. Swap them; the canvas doesn't notice.
- **No "knowledge graph" abstraction.** The graph is just nodes and
  edges. Provenance lives in the regions on disk, not in a separate
  triplestore.
