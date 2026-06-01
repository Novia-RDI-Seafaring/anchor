# Working with documents and canvases

ANCHOR keeps documents and canvases separate: ingest a source document once,
then reuse it on one or more canvases while retaining page and region
provenance.

## 1. Start ANCHOR

```bash
anchor serve --data-dir ~/anchor-data
```

Open <http://127.0.0.1:8002>. The HTTP server is unauthenticated and binds to
loopback by default.

## 2. Ingest a document

Use the canvas upload surface, or ingest a PDF from the command line:

```bash
anchor ingest /path/to/datasheet.pdf --data-dir ~/anchor-data
anchor list --data-dir ~/anchor-data
```

Bronze data stores the original input, silver data contains page extraction,
and gold data contains structured regions when an LLM-backed extractor is
configured.

## 3. Create a canvas

```bash
anchor canvas create pump-analysis --title "Pump analysis" --data-dir ~/anchor-data
anchor canvas state pump-analysis --data-dir ~/anchor-data
```

Canvases are event-backed workspaces. Nodes may contain `source_ref` values so
facts remain linked to document pages or extracted regions.

## 4. Connect an agent

For supported MCP-capable clients:

```bash
claude mcp add --transport stdio --scope user anchor -- \
  anchor-mcp --data-dir ~/anchor-data --base-url http://localhost:8002
anchor install cursor --data-dir ~/anchor-data
```

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
