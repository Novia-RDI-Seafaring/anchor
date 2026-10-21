"""Spec rows on the way in: their names, their claims, and a person's verdict."""
from copy import deepcopy


def normalize_claim_text(value: str) -> str:
    return " ".join(value.split())


def claim_binding(row: dict) -> dict:
    key, value = row.get("key"), row.get("value")
    return {
        "key": normalize_claim_text(key).lower() if isinstance(key, str) else key,
        "value": normalize_claim_text(value) if isinstance(value, str) else value,
    }


def keep_people_verdicts(data: dict, previous: dict | None) -> dict:
    """Keep a row's ``review`` as a person left it, whatever the writer sends.

    A row's ``review`` is a person's verdict on its reference: they looked at
    the source and said it is right or wrong. Only a person gives one, so a
    write by anyone else neither sets nor changes it. The stored verdict stays
    on a row that still makes the same claim from the same source, and goes
    when the claim or the source changes, since it was about the old one.
    """
    rows = data.get("rows")
    if not isinstance(rows, list):
        return data
    old_rows = (previous or {}).get("rows", [])
    old_rows = old_rows if isinstance(old_rows, list) else []
    kept = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            kept.append(row)
            continue
        clean = {k: v for k, v in row.items() if k != "review"}
        old = old_rows[i] if i < len(old_rows) and isinstance(old_rows[i], dict) else {}
        if (
            old.get("review") is not None
            and claim_binding(clean) == claim_binding(old)
            and clean.get("source_ref") == old.get("source_ref")
        ):
            clean["review"] = deepcopy(old["review"])
        kept.append(clean)
    return {**data, "rows": kept} if kept != rows else data


_ROW_NAME_ALIASES = ("label", "name")


def name_rows_by_key(data: dict) -> dict:
    """A row's name lives in ``key``; a row named ``label`` or ``name`` is moved there.

    Rows written with another name field rendered with no name at all, and
    the writer only found out by looking at the canvas. Only a row without
    a usable ``key`` is touched, so an explicit key always wins.
    """
    rows = data.get("rows")
    if not isinstance(rows, list):
        return data
    named = []
    for row in rows:
        if isinstance(row, dict) and not (isinstance(row.get("key"), str) and row["key"].strip()):
            alias = next(
                (a for a in _ROW_NAME_ALIASES if isinstance(row.get(a), str) and row[a].strip()),
                None,
            )
            if alias is not None:
                row = {"key": row[alias], **{k: v for k, v in row.items() if k not in ("key", alias)}}
        named.append(row)
    return {**data, "rows": named} if named != rows else data


def drop_row_checks(data: dict) -> dict:
    """Drop what is left of the automatic claim check from a write.

    Rows once carried ``evidence``: the server's own word on whether the key
    and value matched the cited cell. A reference is right when a reader says
    so (``review``), so a row no longer stores the server's word, and a
    request to check again (``revalidate_evidence``) has nothing to do.
    """
    rows = data.get("rows")
    if not isinstance(rows, list):
        return data
    dropped = [
        {k: v for k, v in row.items() if k not in ("evidence", "revalidate_evidence")}
        if isinstance(row, dict) else row for row in rows
    ]
    return {**data, "rows": dropped} if dropped != rows else data
