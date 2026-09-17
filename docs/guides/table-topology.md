# Table topology and deterministic extraction

PDF cell coordinates use top-left PDF points. Coordinates alone do not prove
that a value belongs to a label. Silver normalization therefore validates
table structure before either ingestion path publishes trusted associations.

Tables carry `table_topology` with a version, status, reason, cell-pair list,
and a digest binding that list to the cells. Cells retain extractor spans,
header flags, and `source_structure` alongside canonical row/column offsets.
The status is `valid`, `reconciled`, `ambiguous`, or `invalid`. Readers report
missing, incompatible, or edited evidence as `unvalidated`.

Validation requires a complete column of physically ordered row anchors.
Every eligible anchor column must agree on a unique assignment. Cell boxes
must belong to the table, occupy consistent columns, and not collide in the
logical grid. A cell touching two row anchors is ambiguous, even if one is
closer. Spans are preserved and constrain validation; reconciliation does not
split, shift, or invent merged cells.

Header flags are preserved. A displaced header candidate is normally
ambiguous. The narrow exception requires an explicit printed `label:` next
to its value, a uniquely validated physical row, a lone preceding heading,
and unflagged body continuation. The association is recorded as
`explicit_label_value`; the header annotation is not erased. Geometry alone
does not turn `Parameter | Model A` into a data pair.

Pointed extraction consumes the certified pairs. Scalar shapes abstain when
a row has multiple value columns or a key/value spans multiple rows. A
column-spanning value may still be one unique cell. A slice includes a whole
intersecting merged cell, and only projects existing pairs; dropping other
columns cannot manufacture a new answer. Repeated identical values do not
resolve an ambiguous key or source.

New pointed references include `detail.table_topology`: the key and value
cell IDs, key text/bbox, canonical row, association basis, and table digest.
These IDs are local to the selected table. They are not document generation
IDs or globally unique citation IDs.

## Existing documents and regeneration

Unversioned gold remains available for inspection but cannot supply new
deterministic pairs or value-cell bbox refinement. Pointed extraction returns
unfilled leaves with `table_warnings`; region inspection exposes the status
and reason. Do not add a version stamp to old cells to bypass validation.

Re-ingest the original PDF through the supported workflow. Use `--force` for
built-in ingestion, or `force=true` when starting a fresh harness session.
An open older harness session must be restarted with force so it receives
new silver candidates. Submit every page and finalize to rebuild gold and
embeddings. Verify the returned key, value, page, and physical source cell.

Rebuild affected silver indexes, raw/polished page Markdown, candidates, gold
regions/content, crops, and embeddings together. Re-running embedding alone
does not repair old table semantics. Existing cached extraction responses and
persisted canvas rows are historical claims: inspect and re-extract affected
rows after regeneration. This patch does not rewrite their values or source
references, replace document identities, or redesign replacement lifecycle.
Search remains a discovery operation, not evidence that an old row is valid.

The validator deliberately abstains on unsupported layouts, missing geometry,
conflicting annotations, and ambiguous spans. Its certificate records the
supported structural interpretation, not a general natural-language truth
verdict or a cryptographic signature from the PDF's author.
