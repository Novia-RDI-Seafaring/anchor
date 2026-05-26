# Anchor v2 — documentation

This folder is the source of truth for what Anchor *is* after the v2
refactor. It's the brief you'd hand a designer who's never seen the
project, or use to redo a poster from scratch.

**Want a hands-on first-day?** Start with [`TUTORIAL.md`](./TUTORIAL.md) — it
walks you from `uv tool install` to "agent fills placeholders" in about
five minutes using a PDF you provide.

The six conceptual documents are small on purpose. Read them in order:

1. **[01-architecture.md](./01-architecture.md)** — the thesis, the
   three substrates, the hexagonal layers. The shape of the system in
   one read.
2. **[02-data-and-events.md](./02-data-and-events.md)** — the workspace
   aggregate, the event envelope, the mutation pipeline, and why
   real-time sync is a free side-effect of getting that pipeline right.
3. **[03-extensions-and-oip.md](./03-extensions-and-oip.md)** — what an
   extension is, what the Open Ingestion Protocol is, and why those two
   things are different.
4. **[04-on-disk-substrate.md](./04-on-disk-substrate.md)** — the
   `data/` folder, line by line. Portable by design.
5. **[05-canvas.md](./05-canvas.md)** — the surface humans and agents
   share. Node types, edges, drop-to-ingest, the runtime registry that
   makes extensions render their own nodes.
6. **[06-many-interfaces.md](./06-many-interfaces.md)** — the visual
   canvas is one of many possible interfaces. Voice, terminal, XR,
   Omniverse, headless monitors — all siblings of the same core, all
   driven by the same event stream and command API.

Illustrations are in [`assets/`](./assets/). Each has a one-line caption
in the markdown that uses it.

## What this is *not*

- Not API reference. Read the code or `oip schema` for that.
- Not a tutorial. A project this young earns one good getting-started in
  the README, not a Read-the-Docs site.
- Not the old poster. The v1 poster was written before the refactor and
  uses pre-refactor names (`card`, "knowledge graph") that no longer
  match the code. Anything that contradicts these docs is wrong.
