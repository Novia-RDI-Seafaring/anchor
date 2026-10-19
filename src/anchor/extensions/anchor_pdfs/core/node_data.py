"""Prepare node data with the same strict evidence policy for create and update."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from anchor.core.workspace.evidence import bind_verified_evidence, claim_binding, evidence_matches
from anchor.core.workspace.merge import deep_merge
from anchor.extensions.anchor_pdfs.core.cell_locate import locate_cell
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content
from anchor.extensions.anchor_pdfs.core.value_provenance import resolve_spec_row_sources


@dataclass(frozen=True)
class PdfNodeDataPreparer:
    store: DocStore

    async def __call__(self, data: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
        intended = deep_merge(previous, data) if previous is not None else data
        # Locate only where the strict check cannot: a row it verifies gets its
        # cell from the certified pair, and its ref is not second-guessed here.
        # One write reads one version of each cited document, across passes.
        store = self.store
        for slug in _cited_slugs(intended):
            store = store.snapshot(slug)
        _, verifiable = await resolve_spec_row_sources(intended, store)
        intended, located = await self._locate_cells(intended, store, skip=set(verifiable))
        diagnostics: dict[int, dict] = {}
        resolved, validations = await resolve_spec_row_sources(
            intended, store, diagnostics=diagnostics,
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
        if resolved == intended and not located:
            return data
        # Keep the caller's patch, including null deletion markers. Passing
        # the full merged state back as a patch would resurrect removed keys.
        return {**data, "rows": resolved["rows"]}

    async def _locate_cells(
        self, intended: dict[str, Any], store: DocStore,
        *, skip: set[int],
    ) -> tuple[dict[str, Any], bool]:
        """Give a row that cites a whole table the cell its value sits in.

        Only for a row that names no box of its own, in a table whose
        structure is valid, so a place someone drew is not reworked and rows
        and columns can be trusted. An older row gains its cell on the next
        write to its card.
        """
        rows = intended.get("rows")
        if not isinstance(rows, list):
            return intended, False
        out, located = list(rows), False
        for i, row in enumerate(rows):
            ref = row.get("source_ref") if isinstance(row, dict) else None
            if i in skip or not isinstance(ref, dict) or ref.get("cell") or ref.get("item_id"):
                continue
            # A box of the caller's own is a claim about the place; leave it.
            detail = ref.get("detail")
            if ref.get("bbox") is not None or (isinstance(detail, dict) and detail.get("cell_bbox")):
                continue
            slug, region_id = ref.get("slug"), ref.get("region_id")
            if not isinstance(slug, str) or not isinstance(region_id, str):
                continue
            try:
                content = await get_region_content(store, slug, region_id)
            except Exception:  # noqa: BLE001 -- locating is a courtesy, never a write failure
                continue
            if not content or content.get("page") != ref.get("page", content.get("page")):
                continue
            # Rows and columns are only trusted where the table's structure is.
            if (content.get("table_topology") or {}).get("status") != "valid":
                continue
            cell = locate_cell(content.get("cells"), row.get("key"), row.get("value"))
            if cell is not None:
                out[i] = {**row, "source_ref": {**ref, "page": content["page"], "cell": cell}}
                located = True
        return ({**intended, "rows": out} if located else intended), located


def _cited_slugs(data: dict[str, Any]) -> list[str]:
    refs = [data.get("source_ref")]
    rows = data.get("rows")
    refs += [r.get("source_ref") for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    slugs = [ref.get("slug") for ref in refs if isinstance(ref, dict)]
    slugs.append(data.get("source_doc_slug"))
    return sorted({s for s in slugs if isinstance(s, str) and s.strip()})
