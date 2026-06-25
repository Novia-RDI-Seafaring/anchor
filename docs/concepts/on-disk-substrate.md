# On-disk substrate

## Goals of the layout

1. **Portable.** `tar` it, mail it, untar it on another machine, run
   `anchor serve --data-dir ./received`. Same canvases, same documents.
2. **Inspectable.** Plain `.json` and `.md`. `cat` works. `jq` works.
   `git log` of the data folder tells a coherent story.
3. **Independently lifecycled.** Documents and canvases don't depend
   on each other. Add or remove either without orphaning the other.
4. **Producer-extensible.** Every extension owns a top-level folder.
   Adding a new extension doesn't change paths owned by existing ones.

## The full tree

The `data/` root below is a project's data directory: the hidden `.anchor_data/`
folder inside the project folder (`<project>/.anchor_data/`, or
`~/.anchor/envs/<env>/projects/<name>/.anchor_data/` for a managed project).
Its internal layout is the same wherever the project lives.

```
data/  ( = the project's .anchor_data/ )
|
+-- canvases/                       (canvas core)
|   +-- <slug>/
|       +-- meta.json               slug, title, created_at, schema_version
|       +-- events.jsonl            append-only event log, one event per line
|       +-- state.json              cached fold of events at the current version
|
+-- bronze/                         (anchor_pdfs)
|   +-- <original-filename>.pdf     raw PDF bytes, flat (no per-slug subfolder)
|
+-- silver/                         (anchor_pdfs)
|   +-- <slug>/
|       +-- index.json              document record: title, filename, page_count, outline
|       +-- pages.meta.json         per-page metadata (dimensions, word counts, ...)
|       +-- ingest-report.json      pipeline outcome: status, stage, region_count, ...
|       +-- pages/
|           +-- <n>.md              polished markdown for page n
|           +-- <n>.raw.md          raw Docling markdown for page n
|           +-- <n>.png             rasterised page image
|           +-- <n>.candidates.json region candidates proposed for page n
|
+-- gold/                           (anchor_pdfs)
|   +-- <slug>/
|       +-- .complete.json          completeness marker: {"complete": true, ...meta}
|       +-- embeddings.json         BGE embeddings for vector search
|       +-- pages/
|           +-- <n>.regions.json    structured regions for page n (id, kind, source_ref, ...)
|           +-- <n>/
|               +-- <region-id>.png cropped screenshot of the region bbox
|
+-- ingest_status/                  (anchor_pdfs, written during active ingestion)
|   +-- <slug>.json                 live activity record: stage, progress, started_at, ...
|
+-- staging/                        (anchor_pdfs, harness-driven ingest sessions)
|   +-- ingest/
|       +-- <session-id>/
|           +-- session.json        session state: slug, steps, status
|           +-- journal.jsonl       per-step append-only log
|           +-- silver/pages/       staged silver pages (pre-publish)
|           +-- gold/pages/         staged gold regions (pre-publish)
|
+-- fmus/                           (anchor_fmus)
|   +-- bronze/
|   |   +-- <slug>.fmu              raw FMU upload
|   +-- models/
|   |   +-- <slug>.json             parsed modelDescription summary (FmuModel)
|   +-- simulations/
|       +-- <sim-id>/
|           +-- run.json            SimulationRun metadata: fmu_slug, params, timestamps
|           +-- series.json         TimeSeries data: signals, time vector
|
+-- cad/                            (anchor_cad)
    +-- bronze/
    |   +-- <slug>.<ext>            raw input model file
    +-- artefacts/
        +-- <slug>/
            +-- document.json       OIP-style document metadata
            +-- model.json          CadModel summary: parameters, parts, geometry
```

## Per-canvas folder, line by line

```
data/canvases/<slug>/
+-- meta.json
|     {
|       "slug": "alfa-laval-eval",
|       "title": "Alfa Laval LKH evaluation",
|       "created_at": 1746000000.0,
|       "schema_version": "0.2"
|     }
|
+-- events.jsonl
|     {"id": "uuid", "ts": ..., "version": 1, "type": "NodeAdded", ...}
|     {"id": "uuid", "ts": ..., "version": 2, "type": "EdgeAdded", ...}
|     ...
|
+-- state.json
      {
        "slug": "alfa-laval-eval",
        "version": 142,
        "nodes": { "n1": {...}, "n2": {...}, ... },
        "edges": { "e1": {...}, ... }
      }
```

`events.jsonl` is the truth. `state.json` is a performance
optimisation: without it a cold boot replays every event from the log;
with it the server reads the snapshot and replays only events that are
newer. Compaction (rewriting the snapshot at checkpoints, optionally
truncating event history) is on the roadmap but not implemented; today
the log grows monotonically.

## Per-document artifact layout (anchor_pdfs)

### Bronze

Bronze stores the raw PDF flat, keyed by the original filename (not the slug).
The silver `index.json` carries the filename so the store can recover the path.

```
data/bronze/
    alfa-laval-lkh.pdf
    grundfos-tp.pdf
    ...
```

### Silver

Silver stores the Docling extraction for each document under a per-slug directory.

```
data/silver/alfa-laval-lkh/
    index.json           document record: slug, title, filename, page_count, outline
    pages.meta.json      per-page metadata (dimensions, word counts, rotation flags)
    ingest-report.json   outcome written at the end of ingest: status, stage, region_count
    pages/
        1.md             polished markdown for page 1
        1.raw.md         raw Docling output for page 1 (pre-polish)
        1.png            rasterised page image (used by the region extractor)
        1.candidates.json region candidates proposed for page 1
        2.md
        ...
```

### Gold

Gold stores structured regions, crops, and embeddings under a per-slug directory.
A `.complete.json` marker is written atomically at the end of a successful gold
pass. A partial or crashed pass leaves the directory without the marker so the
store never presents incomplete gold.

```
data/gold/alfa-laval-lkh/
    .complete.json       {"complete": true, "mode": "keyed", "model": "gpt-5.4", ...}
    embeddings.json      {"embed_model": "BAAI/bge-small-en-v1.5", "dim": 384, "vectors": [...]}
    pages/
        1.regions.json   {"page": 1, "regions": [{id, kind, source_ref, content}, ...]}
        2.regions.json
        ...
        1/
            r0007.png    cropped screenshot of region r0007 on page 1
            r0012.png
            ...
        2/
            ...
```

A region record inside `<n>.regions.json` looks like:

```json
{
  "id": "alfa-laval-lkh:r0007",
  "kind": "spec_block",
  "title": "Pump performance - model LKH-5",
  "source_ref": {
    "kind": "pdf-page-bbox",
    "page": 2,
    "bbox": [72.0, 144.0, 540.0, 312.0]
  },
  "content": {
    "text": "...",
    "rows": [...]
  },
  "crops": {
    "png": "2/r0007.png"
  }
}
```

This is the unit of provenance. **Every value on the canvas points
back to a region.** A spec-table row is a `data` field on a node;
that field carries the region id; the region carries the page and bbox;
the bbox is rendered as a highlight in the PDF viewer. There is no
detached metadata table: the source ref is the data.

### Ingest status

A small live-activity record written as the pipeline advances. It lands
in its own `ingest_status/` directory so it never collides with corpus
artifacts and is trivial to list.

```
data/ingest_status/
    alfa-laval-lkh.json   {"slug": "...", "stage": "gold", "progress": 0.8, ...}
    grundfos-tp.json
```

The record is created when ingest starts and updated after each stage. It
survives a process restart, so an agent polling across process boundaries
gets accurate progress without re-running the pipeline.

### Staging (harness-driven ingest sessions)

In-flight harness-driven sessions live under `staging/ingest/` and are invisible
to `list_documents` until the session is finalized and published to silver/gold.

```
data/staging/ingest/<session-id>/
    session.json          {slug, steps, current_step, status, created_at}
    journal.jsonl         per-step log (one JSON object per line)
    silver/pages/         staged silver pages, same layout as silver/<slug>/pages/
    gold/pages/           staged gold regions, same layout as gold/<slug>/pages/
```

## FMU layout (anchor_fmus)

FMUs use a separate subdirectory tree under `fmus/` inside the data dir.

```
data/fmus/
    bronze/
        <slug>.fmu          raw FMU file
    models/
        <slug>.json         parsed modelDescription summary (FmuModel)
    simulations/
        <sim-id>/
            run.json        SimulationRun: fmu_slug, params, started_at, finished_at
            series.json     TimeSeries: signal names, time vector, values
```

## CAD layout (anchor_cad)

```
data/cad/
    bronze/
        <slug>.<ext>        raw input model file (preserves original extension)
    artefacts/
        <slug>/
            document.json   OIP-style document metadata
            model.json      CadModel: parameters, parts, geometry summary
```

## Why JSONL events instead of a database

- Events are tiny, mostly less than 1 KB. A canvas with 10 000 events is 10 MB.
- One file per workspace makes copying, moving, and diffing trivial.
- An append-only file is the simplest possible crash-safe write.
  No transactions, no migrations, no DBA required.
- A future Postgres or SQLite store is a port (the `WorkspaceStore`
  protocol). The day we need indexed queries across workspaces is the
  day we add a second implementation. The file format stays.

## Multi-tenant note

The current layout assumes one user, one machine. The multi-tenant
roadmap (separate memory entry) adds a `tenants/<tenant>/` prefix and
moves canvases under `tenants/<tenant>/canvases/`. Documents stay
shared by default with opt-in scoping. Nothing in the current paths
needs to change to accommodate that: they become subpaths.
