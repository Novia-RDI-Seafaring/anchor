# Spec source resolution

Node creation and data updates use the same source-resolution policy through
`WorkspaceService`. An optional node-data preparer runs inside the workspace
mutation lock before validation, event persistence and publication. The canvas
core does not know PDF stores or table cells. It manages generic key/value
claim bindings for sourced rows.

`ProjectRuntime` binds `PdfNodeDataPreparer` to its document store. Explicit
HTTP service composition uses the same binding helper. HTTP, MCP and CLI do
not orchestrate source matching. A workspace cannot be rebound to another
store; applications must construct a separate runtime for another corpus.
Without a producer preparer, workspace mutation can invalidate a binding but
cannot issue a new verified verdict.

The PDF preparer consumes explicit success results from `resolve_spec_row_sources`.
The compatibility `enrich_spec_row_source_refs` interface delegates to that same
matcher and still returns only enriched data:

- Explicit document, page, region, geometry and supplied table proof constrain
  resolution. Missing, mismatched, malformed or ambiguous evidence abstains.
- Both printed key and complete value must match one G1-certified pair.
  No value-only search, first-table fallback or fuzzy matching is permitted.
- A valid coarse ref can refine to that pair's value cell. Existing precise
  refs and caller detail are preserved when already equivalent.
- Rows without source scope remain unrefined. Compatible node-level source
  defaults can supply scope under the existing G2 rules.
- Certified-pair metadata is consumed and checked when supplied. A successful
  result records the table digest and certified key/value cell IDs, even when
  an already precise reference needs no geometry change.

R1 author-origin stamping runs first. Newly authored geometry has top-left
semantics; a historical locator copied during update retains its unknown
origin, and explicit null/unknown origins remain unresolved. Newly selected
geometry is stamped top-left. Resolving already resolved data is idempotent.

On update, the preparer resolves the intended post-merge data, including
existing node defaults. It returns the caller's original patch with only
resolved rows overlaid, preserving null deletion markers and omitted fields.
Rows remain whole-list replacements; no partial-row endpoint is introduced.
Move, reparent, label-only, edge and bibliography operations remain unchanged.

Each resolution pins one selected document generation per slug. Multiple page
reads in one operation cannot mix generations if replacement publishes during
the read. This is a point-in-time read, not a transaction between independent
document publication and canvas writes. The next operation selects the then
current generation. Source identity remains slug-owned and hash-addressed;
filename has no authority in matching.

Unchanged enrichment output is not a verified-grounding verdict. The explicit
validation result supports the [claim evidence contract](claim-evidence.md).
Historical links stay unverified until deliberately validated. Substantive
claim edits retain the link but invalidate the old binding.
