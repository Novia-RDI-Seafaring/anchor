# OIP — Open Ingestion Protocol

The OIP specification has moved to its own repository:

**📦 https://github.com/Novia-RDI-Seafaring/OIP**

That repo is the single source of truth for the protocol, manifest schema,
and discovery rules. It also ships a CLI (`uvx oip`) for validating
producer manifests and inspecting compliant on-disk trees.

## What OIP is, in one paragraph

OIP is a small, governance-neutral specification for ingestion tools that
produce structured, source-grounded knowledge. Any tool that conforms to
OIP can be consumed by any OIP-aware application — the same way any
LSP-compliant language server works in any LSP-aware editor. Anchor is the
first reference consumer; Anchor's PDF medallion pipeline is the first
reference producer. Both can be replaced.

## Anchor's relationship to OIP

- **Anchor's canvas** is an OIP **consumer**: it reads OIP-compliant gold
  regions from disk and renders them as canvas nodes with row-level
  provenance.
- **Anchor's bundled producer manifests** currently cover `anchor_pdfs`,
  `anchor_fmus`, and `anchor_cad`. The experimental `anchor_sysml` tools are
  wired into `anchor-mcp`, but its text-to-canvas flow is not yet surfaced by
  `anchor extensions list`.

For the manifest schema, the on-disk tree, the discovery rules, and the
list of source-kinds, **read the OIP repo's spec**. This file used to
contain a draft of that spec; the draft is now superseded by the
versioned spec in the OIP repo and is no longer maintained here.
