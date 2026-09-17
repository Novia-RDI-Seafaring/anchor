# Derived region provenance

`derive_region` resolves its parent through `inspect_region` in one selected
document generation. Use a qualified locator such as `p2/r1` (also `2/r1`).
A bare ID is accepted only when exactly one stored region matches. Missing,
ambiguous or malformed locators are unresolved; derivation raises an error.
Repeated IDs across different pages remain supported through qualification.

The store's page membership supplies the page. The same pinned index supplies
`source_sha256` and `generation_id` when available. Neither filename nor a
nested caller citation determines document identity. Inspect and region-content
responses use this same source contract. Legacy records with missing canonical
geometry or source identity leave those fields unavailable; no historical
geometry conversion or source-identity inference is performed.

A child stores its parent's resolved `source_ref`, a qualified `derived_from`,
and the resolved page and coordinate origin. Bbox and geometry default to the
parent's canonical geometry; producers may supply their own region geometry.
Explicit source-ref fields must agree with the resolved parent, including bbox,
page, slug and available source hash/generation. Compatible supplemental
metadata may be retained. Conflicting source overrides fail before writing.

Inspecting a child returns its own region locator and `derived_from`, so the
same operation can derive another child without a special provenance parser.
`stored_source_ref` exposes the stored parent citation separately for audit;
it does not replace the canonical locator or supply missing geometry. Producer
payload fields remain available under `data`. An ambiguous derivation returns
the candidate pages, and an omitted child ID receives the next free page ID.
A valid region source is not a verified canvas claim (G7 still applies).

Derived regions persist beside their parents and survive restart. Run `embed`
to include them in search. Follow hits using their slug, page and region ID.
Publication during a pinned operation retains G4 behavior: the operation stays
in its selected tree and cannot contaminate a replacement. A caller may need
to retry against the new generation. This change adds no global revalidation,
cross-process write transaction, or duplicate-ID ingest policy.
