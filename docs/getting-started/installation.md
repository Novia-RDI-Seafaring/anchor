# Install and upgrade

For normal use, install the published Python package. It contains the prebuilt
browser UI. Source development additionally needs Node.js and pnpm.

## Install the application

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required for this recipe:

```bash
uv tool install anchor-kb
anchor version
```

`anchor` is the CLI; `anchor-mcp` is the local stdio server launched by your
agent client. If either command is missing from your shell, run
`uv tool update-shell` and reopen the terminal.

Continue with the [Quickstart](quickstart.md) to create an environment and
project before uploading a document. Installing a package or running
`anchor serve` alone does not configure your agent or choose a PDF extraction
provider.

## Optional FMU runtime

```bash
uv tool install --force 'anchor-kb[fmus]'
```

This adds `fmpy` for FMU simulation. Without the runtime, FMU tools fail closed
unless you explicitly enable `ANCHOR_FMU_DEMO=1`. Demo results are synthetic
and marked accordingly.

## Install from source

Use a local checkout when you need unreleased changes. The wheel build hook
requires `web/dist/index.html` and does not run pnpm itself. Build the frontend
before installing:

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor
cd anchor
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv tool install --force .
```

Source frontend builds need Node.js 20+ and pnpm 10. If pnpm is not on PATH,
use `corepack pnpm@10` or `npx pnpm@10` in place of `pnpm`. For example:

```bash
npx pnpm@10 --dir web install --frozen-lockfile
npx pnpm@10 --dir web build
```

Installing directly from a git URL does not perform the required frontend
build. Use the published wheel or the local-checkout recipe above.

## Develop with a checkout

```bash
uv sync --extra dev
pnpm --dir web install --frozen-lockfile
```

In one terminal, start the backend:

```bash
uv run anchor serve
```

In another, start the development UI:

```bash
pnpm --dir web dev
```

Open <http://localhost:5173>. The Vite server proxies API requests to the
backend on port 8002; stop the other listener if that port is occupied before
starting the backend.
Select the environment and project explicitly when serving your own corpus.

## Reinstall or upgrade

Stop `anchor serve` with `Ctrl+C` and close agent clients using `anchor-mcp`
before replacing the installed tool, especially on Windows where an open
executable can prevent replacement.

For the published package:

```bash
uv tool upgrade anchor-kb
anchor version
```

For a rebuilt local checkout:

```bash
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv tool install --force --reinstall .
anchor version
```

An **Access is denied** error during a Windows upgrade usually means a process
still holds the installed executable. Close its client and retry. Do not delete
the tool directory while a process is using it. Project data lives outside the
tool installation; back it up separately before changing ingestion behavior.

## Local model preparation

```bash
anchor models list --env study
anchor models prefetch --env study
```

Create `study` first using the [Quickstart](quickstart.md), or substitute your
environment name. Prefetch needs network access and warms the local model cache.
Local-only extraction uses cached models; a cache miss needs provisioning before
it can succeed offline. A model-assisted gold stage needs either a harness
session or an endpoint-backed provider. See [Provider setup](../guides/provider-setup.md).

## Canvas snapshots

Snapshots require a running canvas server and Playwright Chromium. With the uv
tool installation, install the browser once:

```bash
uv tool run --from anchor-kb playwright install chromium
```

For source development, use `uv run playwright install chromium` instead.
Once the correct project server is running:

```bash
anchor canvas snapshot pump-selection --out canvas.png
```

The MCP snapshotter's `--base-url` must point to the printed server URL when
the server uses another port. See [Agent setup](../guides/agent-setup.md).
