"""Prepare node data with the same strict evidence policy for create and update."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from anchor.core.workspace.evidence import bind_verified_evidence, claim_binding, evidence_matches
from anchor.core.workspace.merge import deep_merge
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.value_provenance import resolve_spec_row_sources


@dataclass(frozen=True)
class PdfNodeDataPreparer:
    store: DocStore

    async def __call__(self, data: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        intended = deep_merge(previous, data) if previous is not None else data
        diagnostics: dict[int, dict] = {}
        resolved, validations = await resolve_spec_row_sources(
            intended, self.store, diagnostics=diagnostics,
        )
        rows = resolved.get("rows")
        if not isinstance(rows, list):
            return data
        rows = list(rows)
        resolved = {**resolved, "rows": rows}
        old_rows = (previous or {}).get("rows", [])
        old_rows = old_rows if isinstance(old_rows, list) else []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            old = old_rows[i] if i < len(old_rows) and isinstance(old_rows[i], dict) else {}
            evidence = row.get("evidence", {})
            validation = validations.get(i)
            requested = row.get("revalidate_evidence") is True
            new_source = intended["rows"][i].get("source_ref") != old.get("source_ref")
            was_verified = evidence.get("status") == "verified" and evidence_matches(row)
            if validation and (requested or new_source or not old or was_verified):
                if was_verified and not requested and evidence.get("validation") != validation:
                    rows[i] = {**row, "evidence": {**evidence, "status": "stale"}}
                else:
                    rows[i] = bind_verified_evidence(row, validation)
            elif evidence.get("status") == "verified":
                rows[i] = {**row, "evidence": {**evidence, "status": "stale"}}
            final = rows[i]
            if requested:
                current_evidence = final.get("evidence") or {
                    "status": "unverified", "claim": claim_binding(final),
                    "source_ref": deepcopy(final.get("source_ref")),
                }
                rows[i] = {**final, "evidence": {**current_evidence, "check": {
                    **diagnostics[i], "claim": claim_binding(final),
                    "source_ref": deepcopy(final.get("source_ref")),
                }}}
            else:
                check = evidence.get("check")
                current_evidence = final.get("evidence", {})
                keep_check = (
                    isinstance(check, dict)
                    and check.get("claim") == claim_binding(final)
                    and check.get("source_ref") == final.get("source_ref")
                    and all(check.get(k) == v for k, v in diagnostics[i].items())
                    and (check.get("status") != "verified"
                         or current_evidence.get("status") == "verified")
                )
                if keep_check:
                    rows[i] = {**final, "evidence": {**current_evidence, "check": check}}
                elif "check" in current_evidence:
                    rows[i] = {**final, "evidence": {
                        k: v for k, v in current_evidence.items() if k != "check"
                    }}
        if resolved == intended:
            return data
        # Keep the caller's patch, including null deletion markers. Passing
        # the full merged state back as a patch would resurrect removed keys.
        return {**data, "rows": resolved["rows"]}
