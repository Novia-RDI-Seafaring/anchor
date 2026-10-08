# Working with documents and canvases

A project contains a document corpus and one or more canvases. Ingest a PDF
once, then reuse it on several canvases. A document card points into that corpus;
a spec table keeps a separate source reference for each row.

## Select the project before you start

For the project created in the [Quickstart](../getting-started/quickstart.md):

```bash
anchor use study pump-study
anchor serve --env study --project pump-study
```

Open the printed URL and leave the server running. CLI commands in another
terminal can use the selection saved by `anchor use`. Commands inside a folder
initialized with `anchor init` resolve that folder's project unless explicitly
overridden. An MCP server is pinned to its environment; the agent selects a
project separately with a tool argument or `open_project`.

## Add a PDF

Drag a PDF onto the canvas, or choose **+ > PDF datasheet**. A document card
shows its progress. The provider determines what happens next:

| Provider | Browser upload behavior |
| --- | --- |
| `local` | The server stores the PDF and runs local extraction. No model-assisted gold regions are created. |
| `harness` | The server stores the PDF, creates an **awaiting agent** card, and queues a `drop_to_ingest` intent. Your agent must complete the harness ingestion session. |
| `ollama`, `openai`, `azure`, `custom` | The server runs local extraction and configured model-assisted processing when the endpoint is available. |

CLI ingestion is also available:

```bash
anchor ingest "/path/to/datasheet.pdf"
anchor list
```

This writes the document corpus, without adding a canvas card. Drag an existing
document from the files explorer onto a canvas to place it. The CLI and MCP
`ingest_pdf` run built-in ingestion; in a harness environment they do not replace
the page-by-page session performed by the agent.

### What the ingestion layers contain

- **Bronze:** the original PDF and source metadata.
- **Silver:** local extraction, page text, rendered pages, layout items, and
  geometry available from Docling.
- **Gold:** interpreted regions and reconstructed region content, when produced
  by a configured extractor or harness session.

Gold-region semantic search needs both gold regions and embeddings. A local-only
document can still be opened, read by page, and cited with available geometry.
Gold is not required for every precise reference: an item, cell, or explicit box
can locate evidence without a gold region.

For built-in ingestion, `silver/<slug>/ingest-report.json` records timing.
`anchor ingests` and `anchor ingest-status SLUG` report ingestion activity.
If a PDF has missing text, try `--full-page-ocr`. To replace an extraction, use
`--force` deliberately; endpoint-backed processing may repeat paid calls.

### Harness-driven ingestion

Ask your agent to check pending intents in the correct project. For an uploaded
PDF it runs `ingest_begin`, retrieves page work items with `ingest_get_page`,
submits interpretations with `ingest_submit_page`, and finishes with
`ingest_finalize`. It then updates the card and resolves the intent.

ANCHOR validates the session output. Region IDs must be unique within a page;
the same ID on different pages is valid. Use qualified locators such as `p2/r4`
when a bare ID is ambiguous. An invalid replacement does not replace the
previous complete document generation. See
[Document generations](../concepts/document-generations.md).

## Navigate a PDF

Open a document in the source dock and choose **Contents** beside **Pages**.
Headings are nested by level; extracted tables and figures have separate lists.
Choose an entry to jump to its page. When the index supplies a bounding box,
the dock briefly highlights that part of the page.

The viewer prefers the extracted silver outline, then tries the PDF's embedded
bookmarks. If neither is available, a short hint points you back to **Pages**.
In **Full screen** quick-look, use the **Contents** button to open the same
navigation panel. Choosing an entry opens its page. Full-screen box overlays
also require page geometry available to quick-look; use the dock for source
review when quick-look reports that page dimensions are unknown.

## Create and organize canvases

```bash
anchor canvas create comparison --title "Pump comparison"
anchor canvas list
anchor canvas state comparison
```

Open the canvas from the browser's canvas list. Add cards and shapes from the
left rail, drag them into place, and use a spec table for related parameters.
The files explorer and PDF source dock can be toggled with `[` while you are
not typing. Canvas state is saved to the project as you work.

Deleting a canvas does not delete its source documents. Removing a document is
a separate corpus operation; existing source links may then fail to resolve.

## Ask an agent to extract information

Name the project, canvas, source document, and desired result:

> In project `pump-study`, add one spec table to canvas `comparison` from the
> ingested datasheet. Include pressure and temperature limits with units and
> product variant. Put a source reference on each row and flag missing values.

For a request tied to visible objects, choose **mark up** (`i`), mark the target,
add your words, and click **send to agent**. The request and subsequent answers
remain in an intent thread. If nothing happens, ask the external agent to pull
pending intents; registering MCP alone does not launch background agent work.

An agent can ask for clarification or stage a suggested change. Inspect the
preview and approve, decline, or send feedback in the thread. Empty placeholders
do not submit work on their own. See the
[tutorial](../getting-started/tutorial.md) for the full review flow.

## Inspect and maintain row evidence

Click a spec row's source anchor to open its PDF page. The dock highlights a
resolvable region, item, cell, or explicit bounding box; a page-only reference
opens the page. Select source text to add a more precise citation when needed.

A highlighted box also opens a small 2.5x magnifier beside it, so a value stays
readable when the page is zoomed out. For a reference with several boxes, move
the pointer over a box to magnify that place. Escape dismisses the highlight
and magnifier together.

| Row state | Meaning |
| --- | --- |
| Verified | The key/value claim matches stored validated evidence within the cited scope. |
| Unverified | A citation exists, but no current validated binding establishes the match. |
| Stale | A previous binding no longer validates, for example after editing the claim or replacing the source. |
| No evidence | The row has no source reference. |

Verify units, conditions, and variant yourself. A clickable citation and a
Verified state do not certify an engineering decision. The row's **Check**
action requests revalidation. Editing a value can keep its citation while
changing its evidence state. See [Claim and evidence](../concepts/claim-evidence.md)
and [Source resolution](../concepts/spec-source-resolution.md).

## Continue later

Stop `anchor serve` with `Ctrl+C`. Your project persists on disk. Start it again
with the same `--env` and `--project`. Back up the whole project folder,
including hidden `.anchor_data/`, rather than only the canvas JSON.

For FMU simulation, install the optional runtime and inspect the model before
wiring table values into its parameters. FMU demo output is synthetic when
`ANCHOR_FMU_DEMO=1`. CAD and SysML support is experimental. See the
[CLI reference](../reference/cli.md) for extension commands.
