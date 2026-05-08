"""Block-level grammar for the SysML v2 Phase-1 subset.

Each function consumes one construct in the block (or block-body) context
and returns the corresponding IR node, or ``None`` when recovery dropped
the construct. Requirement / satisfy / metadata parsers live in
``parser_requirements`` so this module stays under the file-size budget.
"""
from __future__ import annotations

from anchor.extensions.anchor_sysml.core.schemas import (
    IrAttribute,
    IrBlock,
    IrInterface,
    IrPart,
    IrPort,
)
from anchor.extensions.anchor_sysml.infra.lexer import SKIP_KEYWORDS
from anchor.extensions.anchor_sysml.infra.parser_helpers import (
    Cursor,
    expect_ident_like,
    parse_qname,
    read_dotted_path,
    read_literal_until_semi,
    skip_braces,
    skip_brackets,
    skip_construct,
    skip_to_semi,
)
from anchor.extensions.anchor_sysml.infra.parser_requirements import (
    parse_metadata_block,
    parse_requirement,    # re-exported for the top-level driver
    parse_satisfy,        # re-exported for the top-level driver
)


__all__ = [
    "parse_block",
    "parse_metadata_block",
    "parse_requirement",
    "parse_satisfy",
]


# ── Block (part / item def + usage) ──────────────────────────────────────


def parse_block(cur: Cursor) -> IrBlock:
    start = cur.eat()  # `part` or `item`
    is_def = False
    if cur.at_keyword("def"):
        cur.eat()
        is_def = True
    if cur.at_keyword("ref"):
        cur.eat()
        if cur.at_keyword("part"):
            cur.eat()
    name_tok = expect_ident_like(cur, "block name")
    blk = IrBlock(
        kind="block-def" if is_def else "block-usage",
        short_name=name_tok.value,
        qualified_name=name_tok.value,
        source_ref=cur.src(start),
    )
    if cur.at("OP_TYPE"):
        cur.eat()
        blk.typed_as = parse_qname(cur)
    while cur.peek().kind in ("OP_SPECIALIZE", "OP_REDEFINE", "OP_SUBSET"):
        op = cur.eat().kind
        ref = parse_qname(cur)
        if op == "OP_SPECIALIZE":
            blk.specializes.append(ref)
        elif op == "OP_REDEFINE":
            blk.redefines.append(ref)
        else:
            blk.subsets.append(ref)
    if cur.at("LBRACK"):
        skip_brackets(cur)
    if cur.at("SEMI"):
        cur.eat()
        return blk
    if cur.at("LBRACE"):
        cur.eat()
        _parse_block_body(cur, blk)
        cur.expect("RBRACE")
    return blk


def _parse_block_body(cur: Cursor, blk: IrBlock) -> None:
    """Dispatch one block-body member at a time until we hit ``}``."""
    while not cur.at("RBRACE") and not cur.eof():
        t = cur.peek()
        if t.kind == "DOC":
            blk.doc = (blk.doc + "\n" + t.value) if blk.doc else t.value
            cur.eat()
            continue
        if t.kind != "KEYWORD":
            cur.warn(t, f"unexpected token in block body: {t.kind} {t.value!r}; skipping.")
            skip_to_semi(cur)
            continue
        if not _dispatch_block_member(cur, blk, t.value, t):
            cur.warn(t, f"unsupported construct '{t.value}' in block body; skipped.")
            skip_construct(cur)


def _dispatch_block_member(cur: Cursor, blk: IrBlock, kw: str, t) -> bool:
    """Return True when the keyword was handled, False otherwise."""
    if kw == "doc":
        cur.eat()
        if cur.peek().kind == "DOC":
            doc_t = cur.eat()
            blk.doc = (blk.doc + "\n" + doc_t.value) if blk.doc else doc_t.value
        return True
    if kw == "attribute":
        attr = _parse_attribute(cur)
        if attr is not None:
            blk.attributes.append(attr)
        return True
    if kw == "value":
        attr = _parse_attribute(cur, kw_alias="value")
        if attr is not None:
            blk.attributes.append(attr)
        return True
    if kw in ("in", "out", "inout"):
        cur.eat()
        if cur.at_keyword("port"):
            port = _parse_port(cur, direction=kw)
            if port is not None:
                blk.ports.append(port)
        else:
            cur.warn(t, f"'{kw}' is only handled before 'port' in Phase 1; skipped.")
            skip_to_semi(cur)
        return True
    if kw == "port":
        port = _parse_port(cur, direction=None)
        if port is not None:
            blk.ports.append(port)
        return True
    if kw in ("part", "item"):
        sub = _parse_nested_part(cur)
        if sub is not None:
            blk.parts.append(sub)
        return True
    if kw == "ref":
        cur.eat()
        if cur.at_keyword("part"):
            sub = _parse_nested_part(cur, force_ref=True)
            if sub is not None:
                blk.parts.append(sub)
            return True
        cur.warn(t, "'ref' must be followed by 'part' in Phase 1; skipped.")
        skip_to_semi(cur)
        return True
    if kw == "interface":
        iface = _parse_interface(cur)
        if iface is not None:
            blk.interfaces.append(iface)
        return True
    if kw == "metadata":
        md = parse_metadata_block(cur)
        blk.metadata.update(md)
        return True
    if kw == "perform":
        cur.warn_skip("action", t)
        skip_to_semi(cur)
        return True
    if kw in SKIP_KEYWORDS:
        cur.warn_skip(kw, t)
        skip_construct(cur)
        return True
    return False


# ── Attributes / ports / parts / interfaces ──────────────────────────────


def _parse_attribute(cur: Cursor, *, kw_alias: str = "attribute") -> IrAttribute | None:
    cur.eat()  # consume `attribute` (or `value`)
    if cur.at_keyword("def"):
        cur.eat()
    name_tok = expect_ident_like(cur, f"{kw_alias} name")
    typ: str | None = None
    default: str | None = None
    if cur.at("OP_TYPE"):
        cur.eat()
        typ = parse_qname(cur)
    if cur.at("EQ"):
        cur.eat()
        default = read_literal_until_semi(cur)
    if cur.at("SEMI"):
        cur.eat()
    return IrAttribute(name=name_tok.value, type=typ, default=default)


def _parse_port(cur: Cursor, *, direction: str | None) -> IrPort | None:
    cur.eat()  # consume `port`
    if cur.at_keyword("def"):
        cur.eat()
    name_tok = expect_ident_like(cur, "port name")
    typ: str | None = None
    if cur.at("OP_TYPE"):
        cur.eat()
        if cur.at("OP_TILDE"):
            cur.eat()
        typ = parse_qname(cur)
    if cur.at("LBRACK"):
        skip_brackets(cur)
    if cur.at("LBRACE"):
        skip_braces(cur)
    if cur.at("SEMI"):
        cur.eat()
    return IrPort(name=name_tok.value, direction=direction, type=typ)  # type: ignore[arg-type]


def _parse_nested_part(cur: Cursor, *, force_ref: bool = False) -> IrPart | None:
    cur.eat()  # consume `part` or `item`
    if cur.at_keyword("def"):
        skip_construct(cur)
        return None
    name_tok = expect_ident_like(cur, "part name")
    typ: str | None = None
    if cur.at("OP_TYPE"):
        cur.eat()
        typ = parse_qname(cur)
    if cur.at("LBRACK"):
        skip_brackets(cur)
    if cur.at("LBRACE"):
        skip_braces(cur)
    if cur.at("SEMI"):
        cur.eat()
    return IrPart(name=name_tok.value, type=typ, is_ref=force_ref)


def _parse_interface(cur: Cursor) -> IrInterface | None:
    start = cur.eat()  # consume `interface`
    name_tok = expect_ident_like(cur, "interface name")
    typ: str | None = None
    if cur.at("OP_TYPE"):
        cur.eat()
        typ = parse_qname(cur)
    if not cur.at_keyword("connect"):
        if cur.at("SEMI"):
            cur.eat()
        elif cur.at("LBRACE"):
            skip_braces(cur)
        return None
    cur.eat()  # connect
    end_a = _read_endpoint(cur)
    cur.expect("KEYWORD", "to")
    end_b = _read_endpoint(cur)
    if cur.at("SEMI"):
        cur.eat()
    return IrInterface(
        name=name_tok.value, type=typ, end_a=end_a, end_b=end_b,
        source_ref=cur.src(start),
    )


def _read_endpoint(cur: Cursor) -> str:
    """``hullPort ::> hull.highSlot1`` → returns the dotted-path target."""
    expect_ident_like(cur, "endpoint name")
    if cur.at("OP_SUBSET"):
        cur.eat()
        return read_dotted_path(cur)
    return read_dotted_path(cur)
