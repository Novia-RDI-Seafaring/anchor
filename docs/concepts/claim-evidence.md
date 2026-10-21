# Checking a reference

A row's `source_ref` says where its value is printed. Anchor places that
reference as precisely as it can. Whether the reference is right is a
person's call, made from the row's anchor.

## Where a reference points

On every write, the server places each row's reference without judging it:

- Each quote (`source_ref.quotes`) gets the boxes of its words on the page.
- A row that quotes words inside a table gets the cell that holds them.
- A row whose key and value form one printed key/value pair in the cited
  table gets that pair's cell.

Nothing else changes. A reference that cannot be placed stays as written.

## What the writer is told

When quoted words cannot be placed, the write result says why in
`quotes.problems`:

- the words are not on the cited page,
- they are not in the cited cell or region,
- they appear more than once, so the place is ambiguous.

Agents check each value against the cited cell before writing it: the key,
the complete value and its unit as printed. A problem in the result means the
reference points at the wrong place. Fix the reference. Never reword a key or
value to make it fit.

## The person's verdict

Right-click a row's anchor to judge its reference. Choose **Checked, right**
or **Checked, wrong**, with an optional note. The verdict is stored on the row
as `review` (`state`, `by`, `at`, `note`) and shows in the anchor's corner as
✓ or ✕.

Only a person's write sets or changes `review`. An agent's write leaves it as
it was. The verdict stays while the row makes the same claim from the same
source. It is dropped when the key, the value or the source changes, because
it was about the old one.

Accepting or rejecting a whole node or a proposal is a separate action.

## Older canvases

Rows written before this change may carry an `evidence` object from an
automatic check Anchor no longer runs. It is ignored, and the next write to
the row removes it. A `revalidate_evidence` flag in a write is dropped.
