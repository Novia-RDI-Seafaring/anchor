"""Requirement / satisfy / metadata parsers (Phase 1 SysML v2 subset)."""
from __future__ import annotations

from anchor.extensions.anchor_sysml.core.schemas import (
    IrRequirement,
    IrSatisfy,
)
from anchor.extensions.anchor_sysml.infra.parser_helpers import (
    Cursor,
    expect_ident_like,
    parse_qname,
    read_constraint_block,
    read_literal_until_semi,
    read_subject,
    skip_to_semi,
)


def parse_requirement(cur: Cursor) -> IrRequirement:
    start = cur.eat()  # `requirement`
    is_def = False
    if cur.at_keyword("def"):
        cur.eat()
        is_def = True
    req_id: str | None = None
    if cur.at("ANGLE_ID"):
        req_id = cur.eat().value
    name_tok = expect_ident_like(cur, "requirement name")
    req = IrRequirement(
        short_name=name_tok.value,
        qualified_name=name_tok.value,
        req_id=req_id,
        is_def=is_def,
        source_ref=cur.src(start),
    )
    if cur.at("LBRACE"):
        cur.eat()
        _parse_requirement_body(cur, req)
        cur.expect("RBRACE")
    elif cur.at("SEMI"):
        cur.eat()
    return req


def _parse_requirement_body(cur: Cursor, req: IrRequirement) -> None:
    while not cur.at("RBRACE") and not cur.eof():
        t = cur.peek()
        if t.kind == "DOC":
            req.doc = (req.doc + "\n" + t.value) if req.doc else t.value
            cur.eat()
            continue
        if cur.at_keyword("doc"):
            cur.eat()
            if cur.peek().kind == "DOC":
                doc_t = cur.eat()
                req.doc = (req.doc + "\n" + doc_t.value) if req.doc else doc_t.value
            continue
        if cur.at_keyword("subject"):
            cur.eat()
            req.subject = read_subject(cur)
            continue
        if cur.at_keyword("assert"):
            cur.eat()
            if cur.at_keyword("constraint"):
                cur.eat()
            expr = read_constraint_block(cur)
            if expr:
                req.asserts.append(expr)
            continue
        if cur.at_keyword("metadata"):
            md = parse_metadata_block(cur)
            req.metadata.update(md)
            continue
        cur.warn(t, f"unsupported requirement member {t.kind} {t.value!r}; skipped.")
        skip_to_semi(cur)


def parse_satisfy(cur: Cursor) -> IrSatisfy | None:
    start = cur.eat()  # `satisfy`
    requirement = parse_qname(cur)
    if not cur.at_keyword("by"):
        cur.warn(cur.peek(), "expected 'by' in satisfy clause; skipped.")
        skip_to_semi(cur)
        return None
    cur.eat()
    by = parse_qname(cur)
    if cur.at("SEMI"):
        cur.eat()
    return IrSatisfy(requirement=requirement, by=by, source_ref=cur.src(start))


def parse_metadata_block(cur: Cursor) -> dict[str, str]:
    """``metadata { @key = "value"; … }`` — flat ``@key = value`` pairs.

    Phase 2 will interpret structured payloads (notably ISO 15926 RDL URIs).
    Today the value is preserved verbatim as a string.
    """
    cur.eat()  # `metadata`
    out: dict[str, str] = {}
    if cur.at("SEMI"):
        cur.eat()
        return out
    if not cur.at("LBRACE"):
        skip_to_semi(cur)
        return out
    cur.eat()  # {
    while not cur.at("RBRACE") and not cur.eof():
        if cur.at("AT"):
            cur.eat()
            key_tok = expect_ident_like(cur, "metadata key")
            key = "@" + key_tok.value
            value_str = ""
            if cur.at("EQ"):
                cur.eat()
                value_str = read_literal_until_semi(cur)
            out[key] = value_str
            if cur.at("SEMI"):
                cur.eat()
            continue
        skip_to_semi(cur)
    cur.expect("RBRACE")
    return out


__all__ = ["parse_requirement", "parse_satisfy", "parse_metadata_block"]
