# ANCHOR

**A**gent-**N**ative **C**anvas to **H**elp **O**rganize **R**esources.

ANCHOR is a local canvas where you and an external AI agent work with
engineering documents. Add a PDF, ask for one specification table, and inspect
each row's source in the PDF dock. Requests, clarifications, and proposed edits
can stay attached to the canvas objects they concern.

The browser, CLI, and MCP tools use the same persisted project data. ANCHOR runs
on your computer; document disclosure depends on the provider and agent you
choose. A local project folder does not imply that the connected model is local.

## Start here

1. [Install ANCHOR](getting-started/installation.md). The published wheel
   includes the browser UI; Python 3.12+ is required.
2. [Follow the Quickstart](getting-started/quickstart.md). Choose a provider,
   create a project and canvas, connect an agent, and ingest your first PDF.
3. [Work through the tutorial](getting-started/tutorial.md). Build a table,
   check its sources, submit a canvas request, and review an agent's suggestion.

[Open the Quickstart](getting-started/quickstart.md){.md-button .md-button--primary}
[Learn the canvas workflow](getting-started/tutorial.md){.md-button}

## Choose the right workflow

| You want to... | Read |
| --- | --- |
| View and extract a PDF without an ANCHOR API key | [Quickstart](getting-started/quickstart.md) |
| Keep ANCHOR model processing local, or configure an endpoint | [Provider setup](guides/provider-setup.md) |
| Use a working folder or keep several projects | [Environments and projects](guides/environments-and-projects.md) |
| Upload documents, create canvases, and inspect row sources | [Documents and canvases](guides/documents-and-canvases.md) |
| Connect Codex, Claude, Cursor, or another MCP client | [Agent setup](guides/agent-setup.md) and [manual configuration](guides/agent-configuration.md) |
| Understand Verified, Unverified, and Stale rows | [Claim and evidence](concepts/claim-evidence.md) |
| Script operations or discover agent tools | [CLI reference](reference/cli.md) and [MCP reference](reference/mcp.md) |
| Understand storage and service boundaries | [Projects](concepts/projects.md), [architecture](concepts/architecture.md), and [on-disk substrate](concepts/on-disk-substrate.md) |

## What to expect

PDFs are stored as originals plus derived page extraction and, when produced,
interpreted regions. Local Docling extraction works without a model endpoint.
Harness ingestion lets your agent interpret pages. Endpoint-backed ingestion
uses your selected model service. Gold-region semantic search needs gold
regions and embeddings.

Source links make an answer inspectable. Their precision varies from a whole
page to a cell or explicit box. A citation or an automated evidence match does
not certify that a value is suitable for an engineering decision.

FMU simulation needs the optional runtime. CAD and SysML tools are experimental.
The default HTTP server is unauthenticated and binds to loopback; keep it local
unless you provide an authenticated deployment layer.
