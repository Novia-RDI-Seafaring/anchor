# ANCHOR — agent-first knowledge canvas (v2)

This file is the at-a-glance briefing for any agent (Claude Code,
Cursor, Codex, anything else) working on this repo. The conventions
in [`CONTRIBUTING.md`](./CONTRIBUTING.md) apply to agents too; this
file calls out the agent-binding subset.

Harnesses that look for `CLAUDE.md` find a one-line pointer that
lands back here. Single source of truth.

Read [`README.md`](./README.md) for the user-facing intro and
[`docs/01-architecture.md`](./docs/01-architecture.md) for the deep
architecture.

## What this app does

A canvas an AI agent can actually drive. Drop a PDF datasheet into a
workspace, ask the agent for the operating limits, get a grounded spec
table where every value points back to its source page + bbox. Wire
those values into a simulation. **No managed cloud, no vendor lock-in,
data stays on the user's laptop.**

The core workflow:

1. Ingest a technical PDF into the bronze → silver → gold pipeline
2. Drop the resulting document node onto a canvas (or use placeholders)
3. Ask the agent (via MCP) to extract specs, operating data, parameter tables
4. Get grounded, source-referenced spec tables on the canvas
5. Wire values into FMU simulation parameters
6. Run simulations directly from the canvas

## Architecture (v2 — hexagonal modular monolith)

```
src/anchor/
  core/          — pure domain. No httpx, no fastapi, no openai, no pymupdf.
  infra/         — port implementations (fs stores, openai clients, pymupdf, ...)
  adapters/      — http / mcp / cli — all three share one WorkspaceService
  extensions/    — anchor_pdfs / anchor_fmus / anchor_cad / anchor_sysml
web/             — React 19 + Vite + Tailwind v4 + ReactFlow
docs/            — architecture, ingestion, extensions, OIP
tests/           — function-based pytest
```

- **Python**: uv (NOT pip). `uv sync --extra dev` to install everything.
- **Frontend**: `pnpm --dir web ...` (NOT `pnpm --filter`; there is no
  workspace file at the root).
- **Database**: none. Per-workspace folders under `~/anchor-data/canvases/`
  with `meta.json` + `state.json` + append-only `events.jsonl`.
- **Real-time sync**: server-authoritative EventBus → SSE fan-out to
  every connected client. No pgvector, no Postgres, no Redis.
- **Default data dir**: `~/anchor-data` (overridable via
  `--data-dir` or `ANCHOR_DATA_DIR`).

## Canvas node types

| Node type | Purpose |
| --- | --- |
| `document` | PDF / document card with cover image |
| `spec` | Parameter / spec table with row-level source refs |
| `fmu` | FMU model node with inputs/outputs/parameters |
| `cad` | Parametric CAD (jscad/scad) viewer |
| `canvas` | Sub-canvas tile linking to another workspace |
| `concept`, `entity`, `fact`, `area`, `funnel`, `image`, `plot`, etc. | General shapes |

Renderers live under `web/src/canvas/primitives/` and shapes under
`web/src/canvas/shapes/`; the registry mapping `node_type` to a
component is `web/src/canvas/registry.ts`.

## Edge types

- `floating` — loose graph edges (automatic routing)
- `anchored` — explicit handle-to-handle connections (row-level wiring,
  evidence edges)

## Adapter parity rule

**Every new operation must reach HTTP, MCP, and CLI in the same PR.**
Agents and shell users get parity with the UI. See the
`feedback_adapter_parity.md` memory entry for the rationale.

## Document ingestion pipeline (Bronze / Silver / Gold)

Three-layer medallion architecture under `~/anchor-data/`:

| Layer | Path | Contents |
| --- | --- | --- |
| **Bronze** | `bronze/<filename>.pdf` | Raw PDF files |
| **Silver** | `silver/<slug>/` | Docling extraction: items, pages, bboxes |
| **Gold** | `gold/<slug>/` | Structured product knowledge JSON, region crops |

Every region carries `page` + `bbox` (BOTTOMLEFT coordinates from
Docling). The agent's `get_product_data(slug)` tool returns the full
gold JSON in one call.

## FMU runtime

- Real runtime: `fmpy` — `uv pip install 'anchor[fmus]'`.
- Demo runtime: `ANCHOR_FMU_DEMO=1`. Every result is stamped
  `synthetic=true` so the UI can show a `[SYNTHETIC]` badge.
- The extension **fails closed** if neither is available — the previous
  behaviour silently mounted the fake runtime, which was unsafe.

## Security model

The HTTP server is **unauthenticated**. Defaults are loopback-only
(`127.0.0.1`); CORS allows just the Vite dev origins. Workspace slugs
and upload filenames go through `validate_workspace_slug` and
`safe_upload_name`; the filesystem stores re-validate as
defence-in-depth. See `src/anchor/core/upload_safety.py` and
`src/anchor/core/ids.py` for the policy.

## Key design rules

- **FMU nodes are separate from the knowledge graph.** The agent should
  not auto-connect knowledge nodes to FMUs. Manual wiring from spec
  rows to FMU parameters is allowed.
- **Row-level provenance.** Each spec-table row carries its own
  `source_ref` (doc_id, filename, page, bbox). Source edges are visible.
- **One table per extraction.** When extracting operating/spec data,
  produce one grounded table — don't split into many small nodes.

## Development

```bash
# Backend + frontend
uv sync --extra dev
pnpm --dir web install

# Run the server
uv run anchor serve          # http://127.0.0.1:8002
# Or with Vite HMR:
pnpm --dir web dev           # http://localhost:5173, proxies API to 8002

# CLI
uv run anchor demo           # seeds a `demo` workspace with the bundled LKH-5 PDF
uv run anchor canvas list
uv run anchor canvas state <slug>
uv run anchor canvas add-node <slug> spec --label "..." --data '{"rows": [...]}'

# Tests
uv run --extra dev pytest
uv run --extra dev lint-imports
pnpm --dir web test
pnpm --dir web exec tsc --noEmit
```

## Legacy code

The pre-v2 codebase (Next.js + CopilotKit frontend, FastAPI + asyncpg +
pgvector backend, standalone `anchor-canvas` / `anchor-ingest` packages,
paper / poster drafts) lives on the `archive/pre-v2` branch (tag
`pre-v2-cutoff`). Don't revive it on `main` — open it on its own branch
if you need to crib code or context.

## Git workflow (binding for agents)

This repo is **trunk-based**. There is one long-lived branch: `main`.
Every change reaches it through a pull request. The full workflow for
humans is documented in [`CONTRIBUTING.md`](./CONTRIBUTING.md); the
rules below are the agent-binding subset.

**Branch naming.** Pick a prefix based on the change kind:

| Prefix | Used for |
| --- | --- |
| `feat/<topic>` | new functionality |
| `fix/<topic>` | bug fixes |
| `docs/<topic>` | docs / README / CHANGELOG / asset prose |
| `chore/<topic>` | tooling, CI, deps, repo plumbing |
| `refactor/<topic>` | internal restructuring without behaviour change |
| `test/<topic>` | tests only |

**Commit + PR title.** Use Conventional Commits style: `feat: ...`,
`fix(scope): ...`, `docs(readme): ...`. The release pipeline groups
changelog entries by these prefixes.

**The hard rules.**

- **Never push directly to `main`.** Branch protection blocks it, but
  the discipline is to not even try. Always work on a feature branch
  and open a PR.
- **Never force-push to any pushed branch**, including PR branches,
  even with `--force-with-lease`. The system of CI runs + review
  history + audit trail depends on commit hashes staying stable. If a
  PR branch is behind main, use one of:
  1. `gh pr update-branch <number>` — merges main into the PR via the
     GitHub API. Normal push, CI re-runs cleanly.
  2. `git fetch && git merge origin/main` on the PR branch → normal
     push.
  Never `git rebase main && git push --force-with-lease`. If a rebase
  is genuinely needed, ask the user first.
- **Never use `git reset --hard` on a pushed branch.** Same reason.
- **Never skip hooks** (`--no-verify`) or signing flags. If a hook
  fails, fix the issue, don't bypass.
- **CI must be green before merge.** Branch protection enforces it;
  the social contract is to not ask for exceptions.

**Updating a PR branch when it's behind main.** Use:

```bash
gh pr update-branch <pr-number>
```

This is the only correct approach. It performs a merge via GitHub's
API, runs CI on the merge commit, preserves the PR's review history,
and uses a normal push.

**Merging a PR.** Squash-merge is the default (`gh pr merge <n> --squash --delete-branch`).
The squash collapses the PR's commits into one Conventional-Commit
entry on `main`, which is what the changelog / release notes
ingestion expects.

**Releasing.** Releases are tag-driven: bump `pyproject.toml` +
`CHANGELOG.md`, commit, tag `v0.X.Y`, push the tag. The release
workflow does the rest. See [`PUBLISHING.md`](./PUBLISHING.md).

**Legacy code.** The pre-v2 codebase is on `archive/pre-v2` (tag
`pre-v2-cutoff`). Don't revive any of it on `main`.

## Working from GitHub Issues + the roadmap Project

The authoritative task list is **GitHub Issues** in this repo. The
shared cross-agent view is the **Anchor roadmap** Project (v2) under
the org. Issues are the atomic work units; the Project is the board
every agent (human or otherwise) checks first thing.

### Session start

```bash
gh project item-list <number> --owner Novia-RDI-Seafaring
```

Pick something that:

- is in the **Ready** column,
- is labelled **`agent-ready`** (scope crisp, acceptance criteria
  explicit, safe to pick up autonomously),
- is **unassigned**.

Avoid items in **In progress** (someone's on it) and **`needs-design`**
(architectural decisions still open).

### Claiming work

Self-assign and move status before writing any code:

```bash
gh issue edit <n> --add-assignee @me
# Move the card to In progress via the Project UI or `gh project item-edit`.
```

If multiple agents may be working concurrently, comment on the issue
when you start so the activity is visible without polling the
Project board.

### Filing new work mid-session

If you discover a bug, a missing feature, or a doc gap while doing
something else, **file an Issue first** with the appropriate template,
then continue what you were doing. Don't carry the intent in
conversation only — when this session ends, the next agent (or human)
can't see it.

```bash
gh issue create --label type:bug
gh issue create --label type:feature
gh issue create --label type:docs
```

### Linking PRs

PR bodies say `Closes #<n>` (or `Fixes #<n>` for bugs). GitHub
auto-closes the Issue and the Project card moves to **Done** on
merge. No manual cleanup.

### What's an Issue and what's a proposal?

| Open an Issue | Open a `docs/proposals/*.md` PR |
|---|---|
| Default for anything you want done | Only when **all three** apply: |
| | – Cross-cutting (multiple subsystems / extensions) |
| | – Multi-PR (work doesn't fit one PR) |
| | – Re-readable in a year (the *why* matters as much as the *what*) |

If none of the three apply, it's an Issue. Bugs, single-feature adds,
refactors in one area, doc updates — all Issues.

When a proposal is open, file a tracking Issue (*"Track: <proposal
title>"*) and link the proposal from it. Implementation sub-tasks
become child Issues linked to the tracker.

### Labels

| Group | Labels |
|---|---|
| Type | `type:bug`, `type:feature`, `type:docs`, `type:chore`, `type:refactor` |
| Area | `area:canvas`, `area:ingest`, `area:cli`, `area:mcp` |
| Signals | `agent-ready`, `good-first-issue`, `needs-design` |

That's the entire set. Source of truth: `.github/labels.yml`. If a
13th label feels necessary, ask whether the existing ones are doing
their job before adding.
