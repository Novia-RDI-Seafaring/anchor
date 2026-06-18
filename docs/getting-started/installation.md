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

### First run

Create an environment, then serve it:

```bash
anchor init local         # pick an AI provider / data zone (name it whatever you like)
anchor serve              # http://127.0.0.1:8002
```

`anchor init` is the recommended starting point. It creates a named
**environment** (the provider, models, and data zone) and its `default`
project. See
[Environments and projects](../guides/environments-and-projects.md). To make
ANCHOR available to an agent, run `anchor install claude-desktop --env local`.

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

Dev mode runs two processes: one for the backend, one for the frontend with hot-reload.

```bash
# terminal 1
uv run anchor serve

# terminal 2
pnpm --dir web dev
# → backend on :8002, Vite HMR on :5173
```

Storage resolves from the active environment's project. Select it with
`--env` / `--project`, `anchor use`, or `ANCHOR_ENV` / `ANCHOR_PROJECT`. The
config precedence is: explicit flags, `ANCHOR_*` environment variables, the
environment's `.env`, the project `project.toml`, the environment `env.toml`,
then built-in defaults.

## Reinstall or upgrade

Use `--force` when replacing an installed ANCHOR tool with a newer wheel or a
local source checkout:

=== "PyPI"

    ```bash
    uv tool install --force anchor-kb
    ```

=== "Local checkout"

    ```bash
    pnpm --dir web install
    pnpm --dir web build
    uv tool install --force --reinstall --refresh .
    ```

If the published PyPI wheel is behind `main`, install from a local checkout
instead of running `uv tool install anchor-kb`. The local wheel build includes
the React frontend, so build the frontend first:

=== "pnpm on PATH"

    ```powershell
    cd C:\path\to\anchor

    pnpm --dir web install
    pnpm --dir web build

    uv tool install --force --reinstall --refresh .
    anchor serve
    ```

=== "Corepack"

    ```bash
    corepack pnpm@10 --dir web install
    corepack pnpm@10 --dir web build

    uv tool install --force --reinstall --refresh .
    anchor serve
    ```

If Corepack fails with a permission error, install pnpm through npm and run the
same local checkout build:

```powershell
npm install -g pnpm@10
pnpm --dir web install
pnpm --dir web build

uv tool install --force --reinstall --refresh .
anchor serve
```

If global npm installs are blocked by Windows permissions, use a user-local npm
prefix:

```powershell
mkdir $env:USERPROFILE\.npm-global
npm config set prefix "$env:USERPROFILE\.npm-global"
$env:Path = "$env:USERPROFILE\.npm-global;$env:Path"

npm install -g pnpm@10
pnpm --dir web install
pnpm --dir web build

uv tool install --force --reinstall --refresh .
anchor serve
    ```

On Windows, reinstall can fail if an agent harness is still running
`anchor-mcp.exe`:

```text
failed to copy ... anchor-mcp.exe: The process cannot access the file because it is being used by another process
```

Close the MCP client first (Claude Code, Cursor, Codex, OpenCode, or another
client that registered ANCHOR). Then check for leftover ANCHOR processes:

```powershell
Get-Process anchor-mcp -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,Path

Get-Process python -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like '*\uv\tools\anchor-kb\*' } |
  Select-Object Id,ProcessName,Path
```

If those processes are still present after the client is closed, stop only
those ANCHOR tool processes:

```powershell
Get-Process anchor-mcp -ErrorAction SilentlyContinue | Stop-Process

Get-Process python -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like '*\uv\tools\anchor-kb\*' } |
  Stop-Process
```

Then reinstall:

```powershell
uv tool uninstall anchor-kb
pnpm --dir web install
pnpm --dir web build
uv tool install --force --reinstall --refresh .
```

If `uv tool uninstall anchor-kb` reports `Access is denied`, a process is still
holding a file inside the uv tool directory. Repeat the process check above
before trying again. Do not remove `AppData\Roaming\uv\tools\anchor-kb` by hand
while `anchor-mcp.exe` or its Python process is still running.

## Configure gold extraction

The bronze and silver layers run locally without any external service. The gold
layer (structured region extraction) uses an OpenAI-compatible vision model.

The easiest way to configure it is `anchor init` — choose the `openai`, `azure`,
or `custom` provider and it writes the endpoint and models into the
environment's `env.toml`. Then supply the key (never stored in the profile):

```bash
export ANCHOR_OPENAI_API_KEY=sk-...
```

Or set everything by hand in a `.env` or your shell:

```bash
ANCHOR_OPENAI_API_KEY=sk-...
ANCHOR_OPENAI_BASE_URL=https://api.openai.com/v1   # or your Azure / Ollama URL
ANCHOR_REGION_MODEL=gpt-5.4
ANCHOR_POLISH_MODEL=gpt-5.4
```

Without a vision endpoint, `anchor serve` still works. You get silver-layer
extraction (page text, page PNGs, and Docling structure), but gold regions are
skipped.

!!! tip "Where config is read from"
    Settings and storage come from the selected environment, not the working
    directory. Select with `--env` / `ANCHOR_ENV` / `anchor use` (default: the
    environment named in `~/.anchor/default`). The API key lives in
    `ANCHOR_OPENAI_API_KEY` or a gitignored `.env` next to the profile under
    `~/.anchor/envs/<name>/`.

## Verify the install

```bash
anchor version          # -> 0.2.4
anchor canvas list      # -> your existing canvases (empty on a fresh install)
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
