"""Server-owned claim bindings; source links alone carry no validity verdict."""
from copy import deepcopy
from typing import Any

from anchor.core.workspace.merge import deep_merge


def normalize_claim_text(value: str) -> str:
    return " ".join(value.split())


def claim_binding(row: dict) -> dict:
    key, value = row.get("key"), row.get("value")
    return {
        "key": normalize_claim_text(key).lower() if isinstance(key, str) else key,
        "value": normalize_claim_text(value) if isinstance(value, str) else value,
    }


def evidence_matches(row: dict) -> bool:
    evidence = row.get("evidence")
    return (
        isinstance(evidence, dict)
        and evidence.get("claim") == claim_binding(row)
        and evidence.get("source_ref") == row.get("source_ref")
        and bool(row.get("source_ref"))
    )


def prepare_evidence_patch(data: dict, previous: dict | None) -> dict:
    """Discard caller verdicts and carry only persisted claim/evidence pairs.

    Rows have no mandatory stable IDs. Positional comparison is conservative:
    reordering can require revalidation, but cannot transfer verification to a
    different claim or link. No historical scan or verification is performed.
    """
    intended = deep_merge(previous, data) if previous is not None else data
    rows = intended.get("rows")
    if not isinstance(rows, list):
        return data
    old_rows = (previous or {}).get("rows", [])
    old_rows = old_rows if isinstance(old_rows, list) else []
    prepared = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            prepared.append(row)
            continue
        clean = {k: v for k, v in row.items() if k != "evidence"}
        old = old_rows[i] if i < len(old_rows) and isinstance(old_rows[i], dict) else {}
        old_evidence = old.get("evidence")
        if clean.get("source_ref") and old.get("source_ref"):
            changed = claim_binding(clean) != claim_binding(old)
            if isinstance(old_evidence, dict) and old_evidence.get("status") == "stale":
                clean["evidence"] = deepcopy(old_evidence)
            elif changed:
                clean["evidence"] = {
                    **(deepcopy(old_evidence) if isinstance(old_evidence, dict) else {}),
                    "status": "stale",
                    "claim": (old_evidence or {}).get("claim", claim_binding(old))
                    if isinstance(old_evidence, dict) else claim_binding(old),
                    "source_ref": deepcopy(old.get("source_ref")),
                }
            elif evidence_matches(old) and clean.get("source_ref") == old.get("source_ref"):
                clean["evidence"] = deepcopy(old_evidence)
        prepared.append(clean)
    return {**data, "rows": prepared} if prepared != rows else data


def bind_verified_evidence(row: dict, validation: dict[str, Any]) -> dict:
    return {**row, "evidence": {
        "status": "verified", "claim": claim_binding(row),
        "source_ref": deepcopy(row["source_ref"]), "validation": validation,
    }}


def consume_evidence_requests(data: dict) -> dict:
    rows = data.get("rows")
    if not isinstance(rows, list):
        return data
    return {**data, "rows": [
        {k: v for k, v in row.items() if k != "revalidate_evidence"}
        if isinstance(row, dict) else row for row in rows
    ]}
