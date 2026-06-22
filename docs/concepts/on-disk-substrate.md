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
├── canvases/                       (canvas core)
│   └── <slug>/
│       ├── meta.json               slug, title, created_at, schema_version
│       ├── events.jsonl            append-only event log, one event per line
│       └── snapshot.json           cached fold of events at known version
│
├── bronze/                         (anchor_pdfs)
│   └── <slug>/<original>.pdf       raw PDF bytes
│
├── silver/                         (anchor_pdfs)
│   └── <slug>.json                 Docling extraction — items, pages, bboxes
│
├── gold/                           (anchor_pdfs, OIP-shaped)
│   ├── manifest.json               anchor_pdfs's OIP manifest
│   └── artefacts/
│       └── <slug>/
│           ├── document.json       OIP document — title, source_kind, ingested_at
│           ├── regions.json        OIP regions — id, kind, source_ref, content paths
│           └── content/
│               ├── page_001.md     polished markdown per page
│               ├── r0042.png       region screenshot
│               └── r0042.json      structured region data (e.g. spec table rows)
│
├── fmus/                           (anchor_fmus)
│   ├── manifest.json               anchor_fmus's OIP manifest
│   └── artefacts/
│       └── <slug>/
│           ├── document.json       title (model name), source_kind=application/x-fmu
│           ├── regions.json        regions: variables, parameters, simulation results
│           ├── source/<original>.fmu
│           └── content/
│               ├── model.json      parsed modelDescription.xml
│               └── simulations/<sim-id>.json
│
└── .oip/
    └── producers.d/                third-party OIP manifests, per-project scope
        └── <name>.json
```

## Per-canvas folder, line by line

```
data/canvases/<slug>/
├── meta.json
│     {
│       "slug": "alfa-laval-eval",
│       "title": "Alfa Laval LKH evaluation",
│       "created_at": "2026-04-30T08:14:22Z",
│       "schema_version": "0.2"
│     }
│
├── events.jsonl
│     {"id": "uuid", "ts": ..., "version": 1, "type": "NodeAdded", ...}
│     {"id": "uuid", "ts": ..., "version": 2, "type": "EdgeAdded", ...}
│     ...
│
└── snapshot.json
      {
        "version": 142,
        "nodes": { "n1": {...}, "n2": {...}, ... },
        "edges": { "e1": {...}, ... }
      }
```

`events.jsonl` is the truth. `snapshot.json` is a performance
optimisation — without it cold-boot would have to replay every event;
with it the server reads the snapshot and only replays events with
`version > snapshot.version`. Compaction (rewriting the snapshot at
checkpoints, optionally truncating event history) is on the roadmap
but not implemented; today the log grows monotonically.

## Per-document artefact, line by line

A `data/gold/artefacts/alfa-laval-lkh/` produced by `anchor_pdfs` looks
like:

```
document.json
    {
      "slug": "alfa-laval-lkh",
      "title": "Alfa Laval LKH centrifugal pump",
      "source_kind": "application/pdf",
      "source_path": "../../bronze/alfa-laval-lkh/original.pdf",
      "ingested_at": "2026-04-30T08:14:22Z",
      "ingested_by": "anchor-pdfs/0.2.3",
      "size_units": {"page_count": 4, "item_count": 187}
    }

regions.json
    [
      {
        "id": "alfa-laval-lkh:r0007",
        "kind": "spec_block",
        "title": "Pump performance — model LKH-5",
        "source_ref": {
          "kind": "pdf-page-bbox",
          "page": 2,
          "bbox": [72.0, 144.0, 540.0, 312.0]
        },
        "content": {
          "text": "content/r0007.md",
          "image": "content/r0007.png",
          "json": "content/r0007.json"
        }
      },
      ...
    ]

content/
    ├── page_001.md          full polished markdown for page 1
    ├── page_002.md
    ├── r0007.md             markdown for region 7 (a spec block)
    ├── r0007.png            cropped screenshot of the bbox
    ├── r0007.json           structured rows (canonical headers + units)
    └── ...
```

This is the unit of provenance. **Every value on the canvas points
back to a region.** A spec-table row is a `data` field on a node;
that field carries the region id; the region carries the page and bbox;
the bbox is rendered as a highlight in the PDF viewer. There is no
detached "metadata table" — the source ref *is* the data.

## Why JSONL events instead of a database

- Events are tiny, mostly < 1 KB. A canvas with 10 000 events is 10 MB.
- One file per workspace makes copying, moving, and diffing trivial.
- An append-only file is the simplest possible crash-safe write.
  No transactions, no migrations, no DBA required.
- A future Postgres / SQLite store is a port (the `WorkspaceStore`
  protocol). The day we need indexed queries across workspaces is the
  day we add a second implementation. The file format stays.

## Multi-tenant note

The current layout assumes one user, one machine. The multi-tenant
roadmap (separate memory entry) adds a `tenants/<tenant>/` prefix and
moves canvases under `tenants/<tenant>/canvases/`. Documents stay
shared by default with opt-in scoping. Nothing in the current paths
needs to change to accommodate that — they become subpaths.
