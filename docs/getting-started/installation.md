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

Installed? The [Quickstart](quickstart.md) takes you from here to a
source-grounded value in about five minutes, no API key. It covers picking an
environment (your trust boundary), wiring ANCHOR into your harness, and the
first ingest.

For the project model behind it (environments, projects, data zones), see
[Environments and projects](../guides/environments-and-projects.md).

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

If `pnpm` is not installed globally, use one of these forms instead:

```powershell
corepack pnpm@10 --dir web install
# or, with Node.js + npm only:
npx pnpm@10 --dir web install
```

Dev mode runs two processes: one for the backend, one for the frontend with hot-reload.

```bash
# terminal 1
uv run anchor serve

# terminal 2
pnpm --dir web dev
# -> backend on :8002, Vite HMR on :5173
```

With the npm fallback, run the frontend command as:

```powershell
npx pnpm@10 --dir web dev
```

Storage resolves from the active project. Run inside a project folder, or
select by name with `--env` / `--project`, `anchor use`, or `ANCHOR_ENV` /
`ANCHOR_PROJECT`. The config precedence is: built-in defaults, the environment
`env.toml`, the project `anchor.toml` marker, then `ANCHOR_*` environment
variables and flags. The API key stays in `ANCHOR_OPENAI_API_KEY` or the
environment's gitignored `.env`, never in the profile.

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

=== "Node + npm only"

    ```powershell
    cd C:\path\to\anchor

    npx pnpm@10 --dir web install
    npx pnpm@10 --dir web build

    uv tool install --force --reinstall --refresh .
    anchor serve
    ```

    Use this when Node.js and npm are installed, but `pnpm` is not on PATH and
    Corepack fails. `npx pnpm@10` runs pnpm through npm for that command without
    requiring a global pnpm install.

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

## Gold extraction

Bronze and silver run locally with no external service. Gold (structured region
extraction) is where you choose. The recommended no-key path is the `harness`
provider: your agent reads the pages and ANCHOR embeds locally. The
[Quickstart](quickstart.md) walks it end to end.

For server-side extraction with a cloud vision model, use the `openai` or
`azure` provider and a key; see [Quickstart, step 6](quickstart.md#6-optional-server-side-gold-with-openai)
and, for Azure specifics, the
[Azure OpenAI test-drive](../guides/azure-test-drive.md).

!!! tip "Where config is read from"
    Settings and storage come from the selected environment, not the working
    directory. Select with `--env` / `ANCHOR_ENV` / `anchor use` (default: the
    environment named in `~/.anchor/default`). The API key lives in
    `ANCHOR_OPENAI_API_KEY` or a gitignored `.env` next to the profile under
    `~/.anchor/envs/<name>/`.

## Verify the install

```bash
anchor version          # -> the installed version
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
