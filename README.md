# ANCHOR

**A**gent-**N**ative **C**anvas to **H**elp **O**rganize **R**esources.

[![PyPI version](https://img.shields.io/pypi/v/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![Python versions](https://img.shields.io/pypi/pyversions/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

ANCHOR is a local canvas for working with engineering documents alongside an
external AI agent. Add a PDF, ask the agent for one specification table, and
click each row's source anchor to inspect the cited page or region. Requests,
clarifications, and proposed edits can remain attached to the work on the canvas.

The browser, CLI, and MCP tools use the same project data. A project is a folder
containing an `anchor.toml` marker and a hidden `.anchor_data/` directory. An
environment selects the provider and data-handling policy for its projects.
ANCHOR runs on your computer; a connected agent or configured model endpoint
may receive document content.

## First project

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), and an MCP-capable
agent client. The published wheel includes the browser UI, so normal use does
not require Node.js.

This example uses the `harness` provider: your agent interprets PDF pages with
its own model, with no ANCHOR API key. Use a PDF approved for that agent's data
policy. Choose `--provider local` instead for local Docling extraction without
model-assisted gold regions; the [Quickstart](./docs/getting-started/quickstart.md)
explains both paths.

```bash
uv tool install anchor-kb
anchor env create study --provider harness --yes
anchor models prefetch --env study
anchor project create pump-study --env study
anchor use study pump-study
anchor canvas create pump-selection --title "Pump selection"
anchor install codex --env study
anchor serve --env study --project pump-study
```

Use `claude-code`, `claude-desktop`, or `cursor` instead of `codex` for those
clients. Restart or reconnect your agent after registration. Model prefetch
needs network access and can take several minutes; later local processing can
use the cache.

Open the server's printed URL, normally <http://127.0.0.1:8002>, and open
`pump-selection`. Drag a PDF onto the canvas. With `harness`, the card waits
for your agent to handle its ingestion intent. Ask:

> In ANCHOR project `pump-study`, process the pending PDF ingestion intent on
> canvas `pump-selection`. Then create one spec table of the operating limits,
> preserving units and product variant, with a source reference on every row.
> Flag values that the document does not state.

Inspect the resulting row anchors in the PDF dock. A page-only reference opens
the page; a precise locator can highlight the cited cell, item, region, or box.
Check the claim against the source before using it.

For a request about existing canvas objects, use **mark up** (`i`), add words or
drawings, and click **send to agent**. The agent can ask a question or stage a
suggestion in that thread. Review the preview and approve, decline, or send
feedback. An empty placeholder does not submit work by itself. ANCHOR provides
the tools and request queue; your external agent must retrieve the requests.

Follow the [Quickstart](./docs/getting-started/quickstart.md) for the complete
setup and the [tutorial](./docs/getting-started/tutorial.md) for the review flow.

## Pick a provider

| Provider | Interpretation | Where content goes |
| --- | --- | --- |
| `local` | Local Docling extraction; no model-assisted gold regions | ANCHOR processing stays on this computer after local models are cached. |
| `harness` | Your agent interprets pages | To the connected harness and potentially its model provider. No ANCHOR API key. |
| `ollama` | Configured vision model | To your Ollama endpoint, on this computer or another host. |
| `openai`, `azure`, `custom` | Configured vision endpoint | To that endpoint; credentials and model setup are required. |

Gold-region semantic search needs gold regions and embeddings. Local-only
extraction still supplies page text, viewing, and available layout geometry.
An agent can retrieve that content even in a `local` environment, so select
the agent's data policy as well as ANCHOR's provider. See
[Provider setup](./docs/guides/provider-setup.md).

## Where data lives

For a managed project created with `anchor project create`:

```text
~/.anchor/envs/study/
  env.toml
  projects.toml
  projects/pump-study/
    anchor.toml
    .anchor_data/
      bronze/       original PDFs and metadata
      silver/       page extraction, text, rendered pages, and geometry
      gold/         interpreted regions, when produced
      canvases/     saved canvases and event logs
      intents/      persistent agent requests and threads
```

To use your own working folder, run `anchor init pump-study --env study` there
instead of creating a managed project. Back up the whole project folder,
including hidden `.anchor_data/`. Credentials belong to the environment and
are separate from that project backup. See
[Environments and projects](./docs/guides/environments-and-projects.md) and
[On-disk substrate](./docs/concepts/on-disk-substrate.md).

`anchor use` selects CLI defaults. MCP installers pin an environment; the agent
selects a project with `open_project` or a per-call `project` argument. One
browser server serves one project. If data looks empty, compare those selections
using `anchor serve-info`, `list_projects`, and `anchor_status`.

## Learn the application

- [Install and upgrade](./docs/getting-started/installation.md)
- [Documents and canvases](./docs/guides/documents-and-canvases.md)
- [Connect an agent](./docs/guides/agent-setup.md)
- [Manual agent configuration](./docs/guides/agent-configuration.md)
- [CLI reference](./docs/reference/cli.md) and [MCP reference](./docs/reference/mcp.md)
- [Claim and evidence states](./docs/concepts/claim-evidence.md)
- [Architecture](./docs/concepts/architecture.md)

## Extensions and limits

The package includes PDF, CAD, SysML, and FMU extension code. CAD and SysML
support is experimental. FMU simulation requires the optional runtime:

```bash
uv tool install --force 'anchor-kb[fmus]'
```

Without that runtime, FMU simulation fails closed. `ANCHOR_FMU_DEMO=1`
explicitly enables synthetic demo output, which is stamped `synthetic=true`.
Inspect a model before wiring spec rows into simulation parameters.

Producer manifests can be discovered and registered through `anchor extensions`.
Registration alone does not launch or proxy an external producer's MCP server.
See [Extensions and OIP](./docs/concepts/extensions-and-oip.md).

A source link supports review. Automated Verified status reflects a stored
key/value evidence match, not engineering correctness. Changes can leave a row
Unverified or Stale, and a reference may open a whole page rather than an exact
value. Inspect the source and its operating conditions.

The HTTP server is unauthenticated and binds to `127.0.0.1` by default. Keep it
on loopback, or provide authentication through your own deployment layer before
network exposure. Storage is file-based. Shared services provide the same domain
behavior across adapters, while locks and event buses are process-local; avoid
concurrent writes to the same canvas from separate processes.

Run `anchor version` to identify your installation. See
[Releases](./docs/reference/releases.md) and [CHANGELOG.md](./CHANGELOG.md) for
version history.

## Develop from source

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor
cd anchor
uv sync --extra dev
pnpm --dir web install --frozen-lockfile
```

Run `uv run anchor serve` in one terminal and `pnpm --dir web dev` in another.
Open <http://localhost:5173> for the development UI. For a global source install,
build the frontend first with `pnpm --dir web build`, then run
`uv tool install --force .`. Direct git installation does not build the frontend.
See [Install](./docs/getting-started/installation.md#install-from-source).

Checks for contributors:

```bash
uv run --extra dev pytest
uv run --extra dev lint-imports
pnpm --dir web test
pnpm --dir web exec tsc --noEmit
uv run --extra docs mkdocs build --strict
```

The backend follows ports-and-adapters layering. Pure domain code lives in
`src/anchor/core`, I/O in `infra`, protocols in `adapters`, and producer-specific
code in `extensions`. The React UI lives in `web`. Changes go through a branch
and pull request; see [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE).

## Citation

If you use ANCHOR, please cite the software repository:

```bibtex
@misc{ANCHOR,
  author       = {Lamin Jatta and Christoffer Bj{\"o}rkskog and Mikael Manng{\aa}rd and Johan West{\"o}},
  title        = {ANCHOR: Agent-Native Canvas to Help Organize Resources for Traceable Engineering Document Extraction},
  year         = {2026},
  howpublished = {\url{https://github.com/Novia-RDI-Seafaring/anchor}},
}
```

GitHub-compatible citation metadata is provided in
[`CITATION.cff`](./CITATION.cff).

## Acknowledgments

This work was done in the Business Finland funded project
[Virtual Sea Trial](https://virtualseatrial.fi/).

## Contributing

Open changes as short-lived branches targeting `main`; see
[`CONTRIBUTING.md`](./CONTRIBUTING.md). Run `uv run --extra dev pytest` and
`uv run --extra dev lint-imports` before pushing backend changes. See
[`EXTENSIONS.md`](./EXTENSIONS.md) for the proposed third-party extension
contract and its current implementation status.
