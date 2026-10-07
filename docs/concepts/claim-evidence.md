# Claim evidence

A row's `source_ref` is an audit link, not a grounding verdict. The table shows
four states, with visible and accessible text:

| State | Meaning |
| --- | --- |
| Verified | The producer validated this key/value and source at the recorded generation. |
| Unverified | A link exists without an authoritative binding to this claim. |
| Stale | The claim or validated source changed, or revalidation no longer succeeds. |
| No evidence | No row source is present. |

Only Verified uses the green value background and grounded hover marker.
Stale and unverified citations remain clickable. Historical rows without
binding metadata default to Unverified; startup does not rewrite them.

## Binding and ownership

`WorkspaceService` discards caller-supplied evidence verdicts and carries only
the previous persisted binding through generic write preparation. A row's
optional `evidence` contains `status`, normalized `claim` (`key`, `value`), the
validated `source_ref`, and producer `validation`. Absence means unverified
when a source exists. This is deterministic claim identity, not proof of truth.

Normalization is exactly G2's matching contract: collapse whitespace, lowercase
keys, preserve value case. No numeric equivalence, unit conversion or fuzzy
matching is performed. Non-string values cannot obtain PDF verification.

The PDF preparer alone issues new verification after the existing G2 matcher
finds one G1-certified pair within the caller's source scope. The validation
records `producer`, `slug`, `generation_id`, `source_sha256`, `table_digest`,
`key_cell_id` and `value_cell_id`. The source metadata and cells come from the
same pinned document view. Legacy certified gold without generation/source
metadata records null identities; no historical identity is guessed.

On create, valid source-aware rows can become verified. Invalid or ambiguous
sources remain unverified. On update, an unchanged binding stays verified
when current strict validation succeeds. Substantive edits retain the link
and become stale. Supplying different valid source evidence may verify a new
claim. Reverting text alone does not restore verification.

## Deliberate revalidation

Select the spec and click the row's **Check** button. HTTP, MCP and CLI use the
same existing update operation: send the row list with `revalidate_evidence:
true` on the desired row. The server consumes this request flag; it is not
persisted. Success replaces the binding; failure keeps stale/unverified status.
Do not send `evidence.status = verified` as an instruction.

For example, PATCH `/api/workspaces/demo/nodes/spec-id` with:

```json
{"data":{"rows":[{"key":"Pressure","value":"42","source_ref":{"slug":"doc","page":1,"region_id":"pressure"},"revalidate_evidence":true}]}}
```

The same `data` object is accepted by MCP `canvas_update_node` and CLI
`anchor canvas update-node demo spec-id --data <json>`. Rows are whole-list
replacements, so include every row to retain. Revalidation has no second matcher.

## Persistence, edits and limits

Claim and evidence status are stored in one workspace event/snapshot before
SSE publication. Optimistic table rendering checks the claim binding immediately,
so the edited value cannot borrow the old green presentation while awaiting SSE.
Native text-input undo/redo edits the draft only. There is no public committed
canvas undo/redo command. Exact trusted snapshot/event restoration restores the
whole claim/evidence pair without inferring validity from visible text; a normal
update containing copied old metadata must pass strict revalidation again.

Rows have no required stable ID. Positional comparison is conservative and may
require revalidation after reordering; verification cannot transfer to another
claim or link. File-backed workspace locks retain their existing single-process
scope. A document replacement does not scan or invalidate every canvas globally.
The next relevant mutation detects changed generation evidence; untouched rows
show verification at the recorded generation, not a live global truth guarantee.
Publication can occur after a pinned read and before a canvas write. G7 does not
add a cross-document transaction, repair old claims, or implement G8 or later
findings.
