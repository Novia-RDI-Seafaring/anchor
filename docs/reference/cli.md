# CLI reference

The `anchor` command exposes the user-facing local application surface.

## Set up a project

| Command | Purpose |
| --- | --- |
| `anchor init` | Configure the current folder as a project: pick an AI provider / data zone, embedding model, and data dir; write `anchor.toml`. |
| `anchor serve` | Serve the web UI and HTTP/SSE API. If the port is taken, the next free port is used. |

`anchor init` is the recommended first step. After it, run other commands from
inside the folder and they resolve the project automatically — no per-command
`--data-dir`. See [Configuration](configuration.md) for `anchor.toml` and zones.

## Core document commands

| Command | Purpose |
| --- | --- |
| `anchor ingest PDF_PATH` | Run a PDF through the bronze, silver and optional gold pipeline. |
| `anchor list` | List ingested documents. |
| `anchor index SLUG` | Print a document silver index. |
| `anchor regions SLUG` | Print gold-extracted regions. |
| `anchor embed SLUG` | Embed gold regions for semantic search. |
| `anchor search QUERY` | Search embedded gold regions. |
| `anchor synopsis SLUG --entity ENTITY` | Compose an entity-scoped synopsis. |

Commands resolve the data dir from the project (`anchor.toml`) found by walking
up from the working directory, then `ANCHOR_DATA_DIR`, then `~/anchor-data`. An
explicit `--data-dir DIR` overrides all of them.

## Canvas commands

```bash
anchor canvas --help
```

| Command | Purpose |
| --- | --- |
| `canvas list` | List workspaces and reference relationships. |
| `canvas create SLUG` | Create a workspace. |
| `canvas state SLUG` | Print current nodes, edges and metadata. |
| `canvas placeholders SLUG` | List nodes waiting for an agent-populated value. |
| `canvas add-node`, `update-node`, `remove-node` | Mutate canvas nodes. |
| `canvas add-edge`, `update-edge`, `remove-edge` | Mutate edges. |
| `canvas organize`, `align`, `distribute` | Apply layout helpers. |
| `canvas snapshot SLUG` | Render a workspace using a running server and Chromium. |

## Extension commands

| Command group | Purpose |
| --- | --- |
| `anchor sysml` | Render or export SysML text. |
| `anchor fmu` | Inspect and simulate FMUs when the optional runtime is installed. |
| `anchor cad` | Inspect supported CAD models and alter parameters. |
| `anchor extensions` | List and inspect OIP producer manifests. |
| `anchor install <harness>` | Register ANCHOR's MCP server (+ skill) with an AI harness. |

Run `anchor <group> --help` for option-level detail.

`anchor install claude-code` (and `cursor`) register a **folder-resolving** MCP
entry by default — one registration works for every `anchor init` project,
because the server resolves the project from the directory the agent is launched
in. Pass `--data-dir DIR` to pin a single project instead.

For current Claude Code, Codex, OpenCode, Cursor, and generic stdio setup
instructions, see [Agent configuration](../guides/agent-configuration.md).
