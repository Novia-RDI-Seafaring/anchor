# Data and events

## Canvas state

One workspace represents one canvas. The domain `Workspace` holds its slug,
title, version, nodes, edges, metadata, and last event identity. Nodes and edges
are dictionaries in the domain aggregate; the public state response exposes
them as lists:

```json
{
  "slug": "pump-selection",
  "title": "Pump selection",
  "version": 0,
  "nodes": [],
  "edges": [],
  "metadata": {}
}
```

A node has an identity, type, label, position, optional dimensions/parent, and
type-specific `data`. An edge connects two node identities and can name explicit
handles. A spec table stores rows inside node data, with per-row source links
and producer-issued evidence binding when available.

Use `canvas_node_types` or `anchor canvas node-types` to inspect renderer data
contracts. Public source resolution and [claim evidence](claim-evidence.md)
rules are part of preparing those writes, not a separate frontend-only verdict.

## Mutation path

Adapters invoke project services. A workspace mutation loads the current state,
validates the command, prepares source-aware data where relevant, applies domain
events, appends them to the log, saves the state, and publishes updates.
Dependent changes such as removing connected edges are handled by domain rules.

Within a runtime process, workspace locks serialize the mutation sequence.
These locks do not coordinate separate operating-system processes. Avoid
simultaneous writes to the same canvas from independent CLI, MCP, or server
processes.

## Event envelope and types

`DomainEvent` carries an ID, timestamp, per-workspace version, workspace ID,
type, payload, optional causation ID, and optional actor attribution. IDs support
deduplication when the same event identity is resubmitted; do not assume every
newly issued high-level command automatically reuses a previous identity.

Canvas event families include node and edge changes, canvas clearing/snapshots,
reference operations, metadata changes, and proposal-set review. The current
definitions live in `src/anchor/core/events/canvas.py`. Extensions publish
processing events for their own services as well.

## Persistence and replay

Each canvas has:

```text
.anchor_data/canvases/<slug>/
  meta.json
  state.json
  events.jsonl
```

The filesystem store loads the state snapshot and replays logged events newer
than its version. Snapshot writes replace the snapshot file atomically. The
append-only log retains change history and supports reads after a version.
Back up state, metadata, and the log together; a project backup should also
include referenced documents and intent threads.

## Browser synchronization

The browser shares one SSE connection per tab at `GET /api/events?canvas=<slug>`.
It receives a canvas `snapshot`, then `patch` events with domain changes and
`presence` updates. The same stream carries project-wide `intent_pending` count
signals and `ingests` activity lists, including their initial snapshots. A
project-only subscriber can omit `canvas`. Presence uses the `actor_kind` and
`actor_label` query parameters, including the monitor's display label.

One connection keeps two open tabs from filling the browser's HTTP/1 connection
pool and blocking other API requests. Consumers share reconnect and cleanup;
switching canvases replaces the stream and receives a fresh snapshot. The
browser reconciles optimistic edits with persisted state and can re-read a
snapshot after reconnecting or detecting a version gap. The separate workspace,
intent, and ingest SSE endpoints remain available for existing clients.

The HTTP process tails persisted canvas events so writes from CLI and MCP
processes can reach browser subscribers. This bridges file changes into its
in-process event bus. It is not shared-memory synchronization or cross-process
locking, and there is no fixed latency guarantee.

## Intent threads

Intents are durable project-level requests with an origin canvas, optional
targets, and thread items. Markup submissions and harness PDF uploads can create
them. The agent pulls pending intents, posts questions or suggestions, and
resolves completed work. Human answers and review decisions remain attached to
the thread. An empty placeholder node does not create a request.

The inbox notification carries a pending count; clients retrieve payloads
separately. An external harness still has to run the agent and poll or respond
to available signals. See [MCP tools](../reference/mcp.md) and the
[tutorial](../getting-started/tutorial.md).
