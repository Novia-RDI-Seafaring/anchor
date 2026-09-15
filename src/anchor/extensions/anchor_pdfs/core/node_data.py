"""Prepare node data with the same strict evidence policy for create and update."""
from dataclasses import dataclass
from typing import Any

from anchor.core.workspace.merge import deep_merge
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs


@dataclass(frozen=True)
class PdfNodeDataPreparer:
    store: DocStore

    async def __call__(self, data: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        intended = deep_merge(previous, data) if previous is not None else data
        resolved = await enrich_spec_row_source_refs(intended, self.store)
        if resolved == intended:
            return data
        # Keep the caller's patch, including null deletion markers. Passing
        # the full merged state back as a patch would resurrect removed keys.
        return {**data, "rows": resolved["rows"]}
