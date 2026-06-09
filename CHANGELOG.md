# Changelog

All notable changes to Anchor are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Unreleased changes accumulate under `## [Unreleased]` and roll into the
next version section on tag.

## [Unreleased]

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

[Unreleased]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Novia-RDI-Seafaring/anchor/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Novia-RDI-Seafaring/anchor/releases/tag/v0.2.0
