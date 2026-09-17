# PDF replacement generations

A forced replacement of an existing document publishes a complete derived
set. Pages, regions, crops and embeddings from the previous set are not
merged into it. The display filename does not identify either the source or
the generation.

Originals retain their immutable G3 address:
`bronze/<slug>/<sha256>.pdf`. A replacement can have a new source hash;
old original files are retained.

## Storage and publication

`DocStore.begin_replacement` creates a private candidate. Both built-in ingest
and harness finalization write through its `DocStore.replacement` view:

```text
silver/<slug>/.current.json
silver/<slug>/generations/<id>/index.json
silver/<slug>/generations/<id>/pages.meta.json
silver/<slug>/generations/<id>/pages/...
gold/<slug>/generations/<id>/pages/...
gold/<slug>/generations/<id>/embeddings.json
```

The candidate's index records its original source identity. Rendered pages
define the complete page set, including blank pages. Publication requires a
successful report, matching metadata, complete raw/image/candidate artifacts,
gold inside that page set, and embeddings that refer only to candidate gold.
Skipping regions intentionally publishes no old gold or embeddings.

Raw and optional polished page text are produced inside the same candidate.
The successful ingest report lists the pages actually polished by that run.
Publication validates this `polished_pages` inventory against page membership
and existing polished files, then records it in the current generation pointer.
A file found on disk cannot add itself to that inventory.

`publish_replacement` adds the generation id and page set to the index and
atomically replaces `.current.json`. The pointer binds that id, source hash,
page set, initial gold inventory and embedding presence. One pointer selects
both silver and gold, so switching it also switches original-source resolution.
Readers never enumerate historical generation directories for current content.
Missing or inconsistent authoritative source/index metadata fails closed.

Candidates record their parent generation. Publication compares the parent
under the existing filesystem ingest lock. A superseded candidate rejects;
the caller must begin a fresh ingest. Concurrent candidates do not overwrite
each other's trees. Old trees remain readable for already-pinned operations.

## Artifact membership

| Artifact | Replacement behavior |
| --- | --- |
| Index and source metadata | Candidate-owned, switched by the pointer |
| Page metadata, raw text, candidates, images | Complete new rendered page set |
| Polished text | Empty candidate; only polish produced by this run is published |
| Gold and table slices | Empty candidate, populated only by this run |
| Crops | Empty candidate, no inherited old-region images |
| Embeddings | Empty candidate; rebuilt from candidate gold if configured |
| Reports and gold completion marker | Private until publication |
| Ingest activity | Separate progress record, not a publication authority |

`DocStore.snapshot(slug)` pins compound reads and delayed embedding or
derived-region writes. An old embedding job can finish in its old tree but
cannot contaminate the replacement. Standalone embedding rebuilds read only
current gold. Search uses one complete embedding payload per document and
checks its actual model before scoring. Normal derived-region operations may
subsequently extend the selected generation; the pointer's gold inventory is
the publication inventory, not a permanent ban on those existing operations.

Open source panes, full-screen viewers and canvas document cards poll their
index on the existing eight-second UI cadence. A changed generation reloads
the PDF/images and region data and clamps navigation to current pages. This
also handles replacements with the same page count or unchanged source bytes.
Generation query parameters distinguish browser cache entries; filenames are
not cache identity. Until the next successful poll, a browser can still show
its previously loaded complete generation.

## Failures, restart and limits

Extraction, rendering, gold, embedding or pointer-write failure before
publication leaves the previous complete generation authoritative. Harness
session metadata retains the candidate id across restart. Submit, finalize
and abort serialize by session id. If publication succeeds but final session
bookkeeping fails, finalization retry recognizes the published id and completes
bookkeeping without rebuilding the current generation.

This is an atomic filesystem pointer replacement, not a distributed
transaction. It assumes normal local-filesystem rename semantics. There is no
power-loss durability guarantee without fsync, nor a snapshot across multiple
documents or separate HTTP requests. Startup
does not delete abandoned candidates, old trees or original hashes. Garbage
collection is outside this contract. Initial ingestion retains its existing
publication behavior; staging applies when a prior index exists.

## Legacy corpora

Without a pointer, existing corpora retain their legacy read behavior. A
coherent completed corpus remains usable. Stale extra pages, missing pages,
old gold and stale embeddings are not silently repaired from `page_count`.
A successful explicit replacement creates an authoritative new set without
deleting or guessing ownership of historical files. Re-embedding alone does
not repair a legacy mixed corpus; re-extraction/replacement is required.

## Page-text freshness (G5)

`get_page_text` pins the selected generation. It prefers a page's polished
file only when that page is in the pinned publication's `polished_pages`.
Otherwise it returns that generation's raw text, or unavailable if raw is
missing. A missing approved polished file also falls back to raw. Candidate
readers use the successful producer report; before that report they read raw.
Later report changes cannot change the published inventory. New polishing of
a published document requires a fresh ingest generation.

`--skip-polish` and a harness submission without `polished_md` can publish
raw-only. A built-in polisher exception still prevents publication, retaining
the previous complete generation. Optional/mandatory policy is unchanged.
Same-page source replacement never copies old polish. Old generation trees
and pinned readers remain intact; no file deletion is needed for correctness.

Pre-G5 G4 pointers lack the polished inventory and may contain inherited
polish. They conservatively select current raw, even if the old polished file
is present. No timestamp, filename, page number or polish count proves
freshness. Invalid inventory also falls back to raw. Flat legacy corpora
without generation pointers keep their existing compatibility behavior;
explicit replacement establishes the generation contract. There is no
automatic repair of historical claims or files. G6 source enrichment parity
is unchanged.
