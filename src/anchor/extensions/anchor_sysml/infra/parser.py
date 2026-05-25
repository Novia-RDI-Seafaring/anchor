"""Recursive-descent parser for the SysML v2 Phase-1 subset.

Top-level driver: tokenises the source and walks packages. Per-construct
grammar lives in ``parser_grammar`` (block / requirement / satisfy / …),
and reusable cursor + skip / read helpers in ``parser_helpers``.

Why a custom parser instead of pulling in the SysML v2 Pilot ANTLR grammar:
the GfSE pilot grammar is a multi-thousand-line ANTLR4 / Xtext effort
optimised for full v2 conformance. We only handle a documented Phase-1
subset; ~250 lines of recursive descent is sufficient and lets us produce
``Diagnostic`` warnings for constructs we ignore (action / state / …)
without an ANTLR runtime in the core dependency set.
"""
from __future__ import annotations

from anchor.extensions.anchor_sysml.core.schemas import IrModel, IrPackage
from anchor.extensions.anchor_sysml.infra.lexer import SKIP_KEYWORDS, tokenize
from anchor.extensions.anchor_sysml.infra.parser_grammar import (
    parse_block,
    parse_metadata_block,
    parse_requirement,
    parse_satisfy,
)
from anchor.extensions.anchor_sysml.infra.parser_helpers import (
    Cursor,
    ParseError,
    parse_import_path,
    skip_construct,
    skip_to_balanced,
    skip_to_semi,
)


# ── Public API ───────────────────────────────────────────────────────────


class SysmlTextParser:
    """Concrete ``SysmlParser`` over the textual notation."""

    def parse(self, text: str, *, filename: str | None = None) -> IrModel:
        tokens = tokenize(text)
        cur = Cursor(tokens, filename)
        packages: list[IrPackage] = []
        while not cur.eof():
            tok = cur.peek()
            if cur.at_keyword("private", "public"):
                cur.eat()
                continue
            if cur.at_keyword("import"):
                skip_to_semi(cur)
                continue
            if cur.at_keyword("package"):
                try:
                    packages.append(_parse_package(cur))
                except ParseError as exc:
                    cur.warn(exc.token, str(exc), level="error")
                    skip_to_balanced(cur)
                continue
            cur.warn(tok, f"unexpected top-level token {tok.kind} {tok.value!r}; skipping.")
            cur.eat()
        return IrModel(packages=packages, diagnostics=cur.diagnostics)


# ── Package ──────────────────────────────────────────────────────────────


def _parse_package(cur: Cursor) -> IrPackage:
    start = cur.expect("KEYWORD", "package")
    from anchor.extensions.anchor_sysml.infra.parser_helpers import parse_qname

    name = parse_qname(cur)
    pkg = IrPackage(
        qualified_name=name,
        short_name=name.split("::")[-1],
        source_ref=cur.src(start),
    )
    cur.expect("LBRACE")
    while not cur.at("RBRACE") and not cur.eof():
        _parse_pkg_member(cur, pkg)
    cur.expect("RBRACE")
    return pkg


def _parse_pkg_member(cur: Cursor, pkg: IrPackage) -> None:
    t = cur.peek()
    if t.kind == "KEYWORD":
        kw = t.value
        if kw in ("private", "public"):
            cur.eat()
            return
        if kw == "import":
            cur.eat()
            qn = parse_import_path(cur)
            pkg.imports.append(qn)
            skip_to_semi(cur)
            return
        if kw == "package":
            pkg.sub_packages.append(_parse_package(cur))
            return
        if kw in ("part", "item"):
            pkg.blocks.append(parse_block(cur))
            return
        if kw == "requirement":
            pkg.requirements.append(parse_requirement(cur))
            return
        if kw == "satisfy":
            sat = parse_satisfy(cur)
            if sat is not None:
                pkg.satisfies.append(sat)
            return
        if kw == "metadata":
            md = parse_metadata_block(cur)
            pkg.metadata.update(md)
            return
        if kw == "doc":
            cur.eat()
            doc_t = cur.peek()
            if doc_t.kind == "DOC":
                pkg.doc = (pkg.doc + "\n" + doc_t.value) if pkg.doc else doc_t.value
                cur.eat()
            return
        if kw in SKIP_KEYWORDS:
            cur.warn_skip(kw, t)
            skip_construct(cur)
            return
        if kw == "connection":
            cur.warn(t, "top-level 'connection' parsed but not mapped in Phase 1.")
            skip_construct(cur)
            return
    if t.kind == "HASH":
        cur.warn(t, "metadata-tagged construct skipped in Phase 1.")
        skip_construct(cur)
        return
    if t.kind == "DOC":
        pkg.doc = (pkg.doc + "\n" + t.value) if pkg.doc else t.value
        cur.eat()
        return
    cur.warn(t, f"unexpected package member {t.kind} {t.value!r}; skipping token.")
    cur.eat()


# ── Convenience top-level entry ──────────────────────────────────────────


def parse_text(text: str, *, filename: str | None = None) -> IrModel:
    """One-call entry — returns an ``IrModel`` ready for the mapper."""
    return SysmlTextParser().parse(text, filename=filename)


__all__ = [
    "SysmlTextParser",
    "parse_text",
]
