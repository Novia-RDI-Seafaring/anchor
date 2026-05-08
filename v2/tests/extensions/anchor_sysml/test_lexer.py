"""Token-level checks for the SysML v2 lexer."""
from __future__ import annotations

from anchor.extensions.anchor_sysml.infra.lexer import tokenize


def _kinds(text: str) -> list[str]:
    return [t.kind for t in tokenize(text) if t.kind != "EOF"]


def _values(text: str) -> list[str]:
    return [t.value for t in tokenize(text) if t.kind != "EOF"]


def test_keywords_classified():
    kinds = _kinds("package part def attribute port in out inout requirement")
    assert kinds == ["KEYWORD"] * 9


def test_relationship_operators():
    toks = tokenize("Foo : Bar :> Baz :>> Qux ::> Quux")
    kinds = [t.kind for t in toks if t.kind != "EOF"]
    assert "OP_TYPE" in kinds
    assert "OP_SPECIALIZE" in kinds
    assert "OP_REDEFINE" in kinds
    assert "OP_SUBSET" in kinds


def test_qname_separator_distinct_from_subset_op():
    toks = tokenize("Foo::Bar ::> Baz")
    kinds = [t.kind for t in toks if t.kind != "EOF"]
    # `Foo::Bar` should be IDENT QNAME_SEP IDENT, then OP_SUBSET, then IDENT.
    assert kinds == ["IDENT", "QNAME_SEP", "IDENT", "OP_SUBSET", "IDENT"]


def test_angle_id_token():
    toks = tokenize("requirement <'REQ-9942'> totalMass")
    angle = [t for t in toks if t.kind == "ANGLE_ID"]
    assert len(angle) == 1
    assert angle[0].value == "REQ-9942"


def test_doc_block_emitted():
    toks = tokenize("doc /* hello\n   * world */")
    kinds = [t.kind for t in toks if t.kind != "EOF"]
    assert kinds == ["KEYWORD", "DOC"]
    doc_token = next(t for t in toks if t.kind == "DOC")
    assert "hello" in doc_token.value


def test_line_and_block_comments_dropped():
    text = "// line comment\n/* plain block */ part def Pump;"
    kinds = [t.kind for t in tokenize(text) if t.kind != "EOF"]
    # /* … */ becomes a DOC token (the parser may discard it where unwanted),
    # // line comments are dropped entirely.
    assert kinds == ["DOC", "KEYWORD", "KEYWORD", "IDENT", "SEMI"]


def test_position_tracking():
    toks = tokenize("package\n  part def Pump")
    by_value = {t.value: t for t in toks if t.kind != "EOF"}
    assert by_value["package"].line == 1
    # `part` is on line 2, after two spaces of indent
    assert by_value["part"].line == 2
    assert by_value["part"].col == 3


def test_punctuation_and_braces():
    toks = tokenize("{ } [ 1..2 ] ; , = @ #")
    kinds = [t.kind for t in toks if t.kind != "EOF"]
    assert "LBRACE" in kinds
    assert "RBRACE" in kinds
    assert "OP_RANGE" in kinds
    assert "AT" in kinds
    assert "HASH" in kinds


def test_in_out_inout_keywords():
    kinds_in = _values("in port foo")
    kinds_out = _values("out port foo")
    kinds_inout = _values("inout port foo")
    assert kinds_in[0] == "in"
    assert kinds_out[0] == "out"
    assert kinds_inout[0] == "inout"


def test_metadata_at_key_pattern():
    toks = tokenize('metadata { @iso15926-uri = "http://example/x" }')
    kinds = [t.kind for t in toks if t.kind != "EOF"]
    assert "AT" in kinds
    assert "STRING" in kinds
