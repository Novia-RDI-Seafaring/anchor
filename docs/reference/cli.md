# CLI reference

The `anchor` command exposes the user-facing local application surface.

## Core document commands

| Command | Purpose |
| --- | --- |
| `anchor serve` | Serve the web UI and HTTP/SSE API. |
| `anchor ingest PDF_PATH` | Run a PDF through the bronze, silver and optional gold pipeline. |
| `anchor list` | List ingested documents. |
| `anchor index SLUG` | Print a document silver index. |
| `anchor regions SLUG` | Print gold-extracted regions. |
| `anchor embed SLUG` | Embed gold regions for semantic search. |
| `anchor search QUERY` | Search embedded gold regions. |
| `anchor synopsis SLUG --entity ENTITY` | Compose an entity-scoped synopsis. |

Most document commands accept `--data-dir DIR`; use the same data directory
as the running server.

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
| `anchor install` | Register Anchor with Claude Code or Cursor. |

Run `anchor <group> --help` for option-level detail.
