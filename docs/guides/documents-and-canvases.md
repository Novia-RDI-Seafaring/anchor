# Working with documents and canvases

ANCHOR keeps documents and canvases separate: ingest a source document once,
then reuse it on one or more canvases while retaining page and region
provenance.

## 1. Start ANCHOR

```bash
anchor serve
```

Open <http://127.0.0.1:8002>. The HTTP server is unauthenticated and binds to
loopback by default.

## 2. Ingest a document

Use the canvas upload surface, or ingest a PDF from the command line:

```bash
anchor ingest /path/to/datasheet.pdf
anchor list
```

Bronze data stores the original input, silver data contains page extraction,
and gold data contains structured regions when an LLM-backed extractor is
configured.

Each completed ingest writes a timing report at
`<data-dir>/silver/<slug>/ingest-report.json`. The report records total
duration, stage duration, per-page polish timing, per-page gold extraction
timing, and embedding time. Use it when comparing slow and fast runs.

### Built-in ingest vs. harness-driven ingest

ANCHOR has two ways to turn a PDF into usable canvas evidence:

| Mode | Entry points | Gold extraction path | Best fit |
|---|---|---|---|
| Built-in ingest | Canvas drag-drop, HTTP upload, MCP `ingest_pdf`, CLI `anchor ingest` | ANCHOR runs Docling silver extraction and, when configured, a vision extractor for gold regions | Fast normal use and repeatable scripted ingestion |
| Harness-driven ingest | MCP `ingest_begin`, `ingest_get_page`, `ingest_submit_page`, `ingest_finalize` | The connected agent reads each page work item and submits polished markdown plus regions | No-key provider, quality-sensitive tables, or dense datasheets |

Both modes write the same bronze, silver, and gold folders. The difference is
who performs the gold-region interpretation. Drag-drop and `anchor ingest` use
the configured backend extractor. Harness-driven ingest lets the agent review
each page before publishing gold, so it can be slower but more deliberate on
difficult tables.

## 3. Create a canvas

```bash
anchor canvas create pump-analysis --title "Pump analysis"
anchor canvas state pump-analysis
```

Canvases are event-backed workspaces. Nodes may contain `source_ref` values so
facts remain linked to document pages or extracted regions.

## 4. Connect an agent

For supported MCP-capable clients:

```bash
anchor install claude-code   # MCP entry + skill (default env)
anchor install cursor
```

These register a server that resolves the project from the folder you open the
agent in, with no baked data dir and no reinstall per project.

Restart the client after installation. An agent can enumerate workspaces,
search ingested documents, add evidence-backed nodes, and organize a canvas
through the MCP tools.

See [Agent configuration](agent-configuration.md) for Codex, OpenCode, and
generic stdio examples.

## 5. Work without an LLM key

ANCHOR can store PDFs, render pages and manage canvases without an external
LLM. Configure an OpenAI-compatible vision endpoint only when you need
gold-region extraction and grounded semantic lookup.

See [Configuration](../reference/configuration.md) for supported settings and
[MCP tools](../reference/mcp.md) for agent-facing capabilities.
