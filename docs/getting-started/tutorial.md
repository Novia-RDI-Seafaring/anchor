# Tutorial: from a PDF to a reviewed table

This walkthrough continues the [Quickstart](quickstart.md). It assumes project
`pump-study` in environment `study`, canvas `pump-selection`, an ingested PDF,
and an agent connected to the same environment.

## Open the correct project

```bash
anchor use study pump-study
anchor serve --env study --project pump-study
```

Keep the server running and open its printed URL. If it is already running for
this project, use that instance. `anchor serve-info` lists running servers.

Ask the agent to call `list_projects`, then `open_project("pump-study")` or pass
`project="pump-study"` on project-scoped calls. A canvas slug alone does not
identify its project.

## Build a useful table

Tell the agent what you need and which source to use:

> On canvas `pump-selection` in project `pump-study`, make one specification
> table from the pump datasheet. Include operating limits, units, and the
> relevant product variant. Each row must link to the source page and the most
> precise available locator. Do not infer unstated values.

With gold regions, the agent can search regions and retrieve their reconstructed
content. With local-only extraction, it can inspect page text and available
layout geometry. Semantic gold-region search is unavailable without gold
regions and embeddings. Reading through an agent exposes that content to its
configured model, even if the ANCHOR environment uses `local`.

An agent can add or update the table through MCP. The browser reads the same
persisted canvas and refreshes through server-sent events.

## Check the evidence

Click the source anchor beside a row. Inspect the PDF in the source dock:

1. Check that the value belongs to the right parameter and product variant.
2. Check the units and any operating conditions or footnotes.
3. If the reference opens a whole page, locate the value yourself. Selecting
   text can pin a more precise box to the row.
4. Correct the table or ask the agent to revise it when the claim is wrong.

Rows distinguish **Verified**, **Unverified**, **Stale**, and **No evidence**.
Verified means ANCHOR matched the row's key and value to stored validated
evidence. It is not an engineering approval. A substantive edit can make a
previously verified row stale while keeping its source link. Use the row's
**Check** action to request revalidation against the current stored evidence.
See [Claim and evidence](../concepts/claim-evidence.md) for the matching limits.

## Make a request on the canvas

Use the **mark up** tool on the left rail, or press `i` while you are not typing.
Mark the objects or rows you mean and write a specific request, for example:

> Check the units in these rows and add the cited operating conditions.

Click **send to agent**. The remark stays on the board with its thread. It
becomes a durable project-level intent that your agent can retrieve. Ask the
agent to check pending intents for `pump-study` if it is not already doing so.
ANCHOR does not run an agent or guarantee that your client continuously polls.

An empty shape or a node marked as a placeholder identifies a possible target;
it does not, by itself, submit a request. A valid submitted ask needs text or
meaningful drawing content.

## Review the response

The agent may ask a question in the remark thread. Answer it there so the
clarification stays attached to the request.

For a suggested canvas change, inspect the preview and choose **approve** or
**decline**. You can send further marks or text as feedback. Applied small
changes may offer **keep** and **revert** controls in the same thread. These
controls concern that change; they are not a general canvas undo history.

Agent-created nodes can also use the canvas review mode and proposal sets.
Those group added elements for review and are separate from intent-thread
suggestions. The resulting table remains editable by you.

## Reuse the project

In a second terminal:

```bash
anchor use study pump-study
anchor list
anchor canvas list
anchor canvas state pump-selection
anchor intents
```

The corpus belongs to the project, so one document can support several canvases.
Stop the server with `Ctrl+C`; restart it with the same environment and project
to continue. Copy the whole project folder, including `anchor.toml` and
`.anchor_data/`, for a filesystem backup. An environment's credentials are
separate from the project.

## Optional: explore the demo canvas

`anchor demo` seeds a canvas called `demo` with six placeholder spec nodes and
starts a server. It can ingest an optional local sample PDF if one is available;
the public package does not ship a vendor datasheet. Check which project the
command resolves before using it for real work. The demo's empty nodes still
need an explicit request before an agent fills them.

## Next steps

- [Documents and canvases](../guides/documents-and-canvases.md): upload modes,
  source references, and common commands.
- [Provider setup](../guides/provider-setup.md): local, harness, and endpoint
  extraction choices.
- [Environments and projects](../guides/environments-and-projects.md): working
  folders, named projects, and storage selection.
- [Agent setup](../guides/agent-setup.md): client installers and troubleshooting.
