# Install

Two paths, depending on whether you want to *use* ANCHOR or *hack on it*.

## Use it (from PyPI)

=== "uv (recommended)"

    ```bash
    uv tool install anchor-kb
    anchor serve              # http://127.0.0.1:8002
    ```

=== "pipx"

    ```bash
    pipx install anchor-kb
    anchor serve
    ```

=== "pip in a venv"

    ```bash
    python -m venv .venv && source .venv/bin/activate
    pip install anchor-kb
    anchor serve
    ```

`anchor` and `anchor-mcp` are now on your PATH globally. The wheel includes the prebuilt frontend, so no Node toolchain is required to just run it.

Requires Python 3.12+. CI tests Linux and runs CLI smoke checks on macOS and
Windows; verify browser and PDF workflows on your target platform.

## Optional extras

| Extra | Install | Adds |
|---|---|---|
| `fmus` | `uv tool install 'anchor-kb[fmus]'` | FMU simulation runtime (`fmpy`). Without it, FMU tools fail closed unless you opt into the synthetic demo with `ANCHOR_FMU_DEMO=1`. |

## Hack on it (from source)

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor
cd anchor
uv sync --extra dev          # adds pytest, ruff, import-linter
pnpm --dir web install
```

Dev mode runs two processes — one for the backend, one for the frontend with hot-reload:

```bash
# terminal 1
uv run anchor serve

# terminal 2
pnpm --dir web dev
# → backend on :8002, Vite HMR on :5173
```

Commands default `--data-dir` to `~/anchor-data`. Use the same explicit
`--data-dir` for server, ingest and agent registration when you keep project
data elsewhere.

## Configure gold extraction

The bronze and silver layers run locally without any external service. The gold layer (structured region extraction) uses an OpenAI-compatible vision model. To enable it, create a `.env` file with your provider details:

```bash
ANCHOR_OPENAI_API_KEY=sk-...
ANCHOR_OPENAI_BASE_URL=https://api.openai.com/v1   # or your Azure / Ollama URL
ANCHOR_REGION_MODEL=gpt-5.4
ANCHOR_POLISH_MODEL=gpt-5.4
```

Without these, `anchor serve` still works — you get silver-layer extraction (page text + page PNGs + Docling structure) but gold regions are skipped.

!!! tip "Where the `.env` is read from"
    `pydantic-settings` loads `.env` from the working directory at boot. For globally-installed `anchor`, run the server from the directory containing your `.env`, or set the variables in your shell.

## Verify the install

```bash
anchor version          # → 0.2.0
anchor canvas list      # → your existing canvases (empty on a fresh install)
```

## Canvas snapshots

Snapshot rendering uses Playwright Chromium and requires a running ANCHOR
server. Install the browser once before using `anchor canvas snapshot`:

```bash
playwright install chromium
anchor serve
anchor canvas snapshot demo --out demo.png
```

## Release process

ANCHOR uses tag-driven releases via PyPI's OIDC trusted publishing. Maintainers: see [`PUBLISHING.md`](https://github.com/Novia-RDI-Seafaring/anchor/blob/main/PUBLISHING.md) in the repo for the full procedure.
