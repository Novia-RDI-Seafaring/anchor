# Quickstart

Create a project, open a canvas, and ask your agent to build a specification
table from a PDF. You need Python 3.12+, [uv](https://docs.astral.sh/uv/), and
an MCP-capable agent client for the agent steps.

## 1. Install ANCHOR

```bash
uv tool install anchor-kb
anchor version
```

The published wheel includes the browser UI. You do not need Node.js for normal
use. If `anchor` is not found, run `uv tool update-shell`, reopen the terminal,
and retry. See [Install](installation.md) for source builds and upgrades.

## 2. Choose how the PDF will be read

An **environment** stores the provider configuration. A **project** holds your
documents and canvases. Each project belongs to one environment.

| Provider | Who interprets regions on the page? | What to expect |
| --- | --- | --- |
| `harness` | Your connected agent | No ANCHOR API key. Page content reaches your agent and potentially its model provider. |
| `local` | Local Docling layout extraction only | Page text, layout geometry, and PDF viewing; no model-assisted gold regions or gold-region semantic search. |
| `ollama` | Your configured vision model | Model calls go to your Ollama endpoint, which can be on this computer or another host. |
| `openai`, `azure`, `custom` | A configured vision endpoint | Requires endpoint setup and credentials. Content is sent to that endpoint. |

This walkthrough uses `harness`. Choose it for a PDF you can share with your
agent's model provider. For local processing, use `--provider local` in the
next command; step 5 explains the different upload behavior. Read
[Provider setup](../guides/provider-setup.md) for endpoint-backed extraction.

```bash
anchor env create study --provider harness --yes
anchor models prefetch --env study
```

Prefetch downloads the local extraction and embedding models once. It needs
network access and may take several minutes. It does not ingest your PDF.

## 3. Create a project and canvas

```bash
anchor project create pump-study --env study
anchor use study pump-study
anchor canvas create pump-selection --title "Pump selection"
```

`anchor use` selects the project for subsequent CLI commands. It does not
select the agent's MCP project. You will name `pump-study` in the agent request.
The managed project lives under
`~/.anchor/envs/study/projects/pump-study/`, with its files in `.anchor_data/`.

Prefer to keep a project in your own working folder? Run
`anchor init pump-study --env study` there instead of `anchor project create`.
See [Environments and projects](../guides/environments-and-projects.md).

## 4. Connect your agent and start the browser

Run the installer for the client you use:

```bash
anchor install codex --env study
```

Other built-in targets are `claude-code`, `claude-desktop`, and `cursor`.
Replace `codex` with your target. Restart or reconnect the client so it loads
the MCP server. The installer registers ANCHOR; it does not start an agent.
See [Agent setup](../guides/agent-setup.md) for what each installer writes.

```bash
anchor serve --env study --project pump-study
```

Leave this terminal running. Open the URL printed by the server, normally
<http://127.0.0.1:8002>, then open the `pump-selection` canvas. Its usual direct
URL is <http://127.0.0.1:8002/c/pump-selection>. If port 8002 is occupied,
the command fails with the bind reason. Choose another port with `--port N`,
or add `--port-walk` to select a free port and print its URL.

## 5. Add your PDF

Drag a PDF from your computer onto the canvas, or use **+ > PDF datasheet**.
The upload creates a document card.

With `harness`, the card displays **awaiting agent**. The upload saves the PDF
and queues an ingestion request; an external agent must process it. Ask your
agent:

> Use ANCHOR project `pump-study` in environment `study`. Check the pending
> intents and process the PDF dropped on canvas `pump-selection`. Complete
> the harness ingestion session, update the document card, and resolve the
> ingestion intent. Tell me whether extraction completed and how many regions
> are available.

The agent uses `ingest_begin`, reads page work items with `ingest_get_page`,
submits interpretations with `ingest_submit_page`, and publishes them with
`ingest_finalize`. ANCHOR validates the submitted regions and derives their
content from stored extraction geometry. The session is not an automatic
consequence of connecting an MCP server.

With `local`, the server runs Docling extraction itself. The PDF becomes
available for page text and source viewing without gold regions. You can also
ingest through the CLI in another terminal:

```bash
anchor use study pump-study
anchor ingest "/path/to/datasheet.pdf"
anchor list
```

Use your actual path, such as `"C:/Users/you/Downloads/datasheet.pdf"` on
Windows. CLI ingestion adds the document to the project corpus; it does not
place a document card on the canvas. Drag the document from the files explorer
onto the canvas when you need a card. In a `harness` environment, CLI ingestion
alone does not run the agent's page-by-page gold session.

## 6. Ask for one source-linked table

Once the PDF is ready, ask your agent:

> In ANCHOR project `pump-study`, use the ingested datasheet to create one spec
> table on `pump-selection`. Include maximum inlet pressure, temperature
> limits, and operating speed if the document states them. Keep the units and
> product variant. Give every row its own source reference. Leave missing
> values explicitly unresolved.

The table appears on the canvas. Click a row's source anchor to open the PDF
page and, when a precise locator is available, highlight the cited area.
Page-only references open the page without a precise highlight. A source link
supports inspection; it does not establish that the extracted claim is correct.

Compare the key, value, units, and product variant against the source. See
[Working with documents and canvases](../guides/documents-and-canvases.md) for
row evidence states and [the tutorial](tutorial.md) for canvas requests and
proposal review.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Document stays **awaiting agent** | Ask the connected agent to pull pending intents for `pump-study` and run the harness ingestion session. |
| Agent sees an empty project | Ask it to call `list_projects` and `anchor_status`, then use `project="pump-study"` or `open_project("pump-study")`. CLI `anchor use` does not retarget MCP. |
| No gold regions or semantic search results | Expected with `local`. With `harness`, finish the ingestion session. With an endpoint provider, check the provider and credentials, then re-ingest deliberately. |
| Local model loading fails | Run `anchor models prefetch --env study` while online; inspect its errors before retrying ingestion. |
| PDF text is missing | Try built-in ingestion with `anchor ingest "/path/to/file.pdf" --full-page-ocr --force`. |
| Browser shows a different project | Check `anchor serve-info`; restart the server with explicit `--env study --project pump-study`. |
| Source link opens only a page | The reference has no resolvable region, item, cell, or explicit box. Inspect the page and add a text selection as evidence when needed. |

For confidential PDFs, cached local ingestion can keep ANCHOR's model processing
on this computer. Connecting a remote agent still lets that agent retrieve
document content. Choose both the environment and the agent accordingly.
