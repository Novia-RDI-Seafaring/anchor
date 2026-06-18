# CLI reference

The `anchor` command exposes the user-facing local application surface.

## Set up environments and projects

| Command | Purpose |
| --- | --- |
| `anchor init [name]` | Create an environment (provider / data zone / models) and its `default` project. Writes `env.toml`. Self-corrects an Azure endpoint missing `/openai/v1/` and offers to save the key to a gitignored `.env`. |
| `anchor env create / list / show / default` | Manage environments. `create` is the provider picker (same as `init`); `list` shows them (`*` marks the default); `default` sets the default. |
| `anchor project create / list / set-description / move` | Manage projects inside an environment. `move --to <env>` relocates a corpus across environments, confirming the zone change. |
| `anchor use <env> [project]` | Set a session default so later commands can omit `--env` / `--project`. |
| `anchor migrate` | Fold a pre-existing `~/anchor-data` into the default environment's `default` project. |
| `anchor check --env <name>` | Verify the resolved data zone: provider / endpoint / project dir / models / key, repair a malformed endpoint (`--fix`), and with `--probe` confirm the deployment + key. Exits non-zero when something would break. |
| `anchor serve` | Serve the web UI and HTTP/SSE API for the selected project. |

`anchor init` is the recommended first step, then `anchor check`. Select the
environment and project with `--env` / `--project`, `anchor use`, or
`ANCHOR_ENV` / `ANCHOR_PROJECT`. Every flag of `anchor init` is scriptable
(`--yes --provider … --base-url … --vision-model …`), so an agent can scaffold
an environment the way it runs `npm init`. See
[Environments and projects](../guides/environments-and-projects.md) and the
[Azure OpenAI test-drive](../guides/azure-test-drive.md) for the full Azure flow.

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

Commands resolve storage from the selected environment and project, in order:
`--env` / `--project` > `ANCHOR_ENV` / `ANCHOR_PROJECT` > the `anchor use`
selection > the default environment and its `default` project. An explicit
`--data-dir DIR` overrides for a single command.

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

`anchor install claude-code` (and `cursor`, `claude-desktop`) register an MCP
entry pointing at an environment (`--env <name>`, default the default
environment). `claude-desktop` supports a named entry per environment
(`--name`), so you can register more than one; see the command's `--help`.

For current Claude Code, Codex, OpenCode, Cursor, and generic stdio setup
instructions, see [Agent configuration](../guides/agent-configuration.md).
