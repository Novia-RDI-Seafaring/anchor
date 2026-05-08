"""Tokeniser for the SysML v2 subset we support in Phase 1.

A flat token stream is produced from the source text — keywords, identifiers,
operators, literals, doc-comments, and angle-bracketed ids (``<'REQ-42'>``).
Block structure is recovered later by the parser using brace nesting.

Why a custom lexer instead of pulling in the SysML v2 Pilot grammar:
the GfSE pilot grammar is a multi-thousand-line ANTLR4 / Xtext effort
optimised for full v2 conformance. We only handle a documented Phase-1
subset; a scanner of ~250 lines is sufficient and lets us produce
``Diagnostic`` warnings for constructs we ignore (action / state /
transition / flow / calc) without an ANTLR runtime in the core deps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from anchor.extensions.anchor_sysml.infra.lexer_tables import (
    ANGLE_ID,
    ANNOTATION_NAME,
    DOC_COMMENT,
    IDENT,
    KEYWORDS,
    LINE_COMMENT,
    NUMBER,
    PUNCT,
    SKIP_KEYWORDS,
    STRING,
)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    col: int


class LexError(ValueError):
    """Raised on a character the scanner cannot handle (rare in practice)."""


def tokenize(text: str) -> list[Token]:
    """Produce the full token list for ``text``.

    Stable ``(line, col)`` positions are kept so the parser can attach them
    to ``SourceRef``. Line comments and non-doc block comments are dropped.
    ``doc /* … */`` does emit a DOC token because the parser needs the
    payload.
    """
    return list(_iter_tokens(text))


def _iter_tokens(text: str) -> Iterator[Token]:
    pos = 0
    line = 1
    col = 1
    n = len(text)
    while pos < n:
        ch = text[pos]
        # Whitespace + newline tracking.
        if ch == "\n":
            pos += 1
            line += 1
            col = 1
            continue
        if ch in " \t\r":
            pos += 1
            col += 1
            continue
        # // line comment
        if text.startswith("//", pos):
            m = LINE_COMMENT.match(text, pos)
            assert m is not None
            consumed = m.end() - pos
            pos = m.end()
            col += consumed
            continue
        # /* … */ — emit a DOC token (the parser drops it where unwanted).
        if text.startswith("/*", pos):
            m = DOC_COMMENT.match(text, pos)
            if m is None:
                raise LexError(f"unterminated block comment at line {line}")
            yield Token("DOC", m.group(1).strip(), line, col)
            line, col = _advance(m.group(0), line, col)
            pos = m.end()
            continue
        # angle-id  <'REQ-42'>  /  comparison ops < <= > >=
        if ch == "<":
            m = ANGLE_ID.match(text, pos)
            if m is not None:
                yield Token("ANGLE_ID", m.group(1), line, col)
                consumed = m.end() - pos
                pos = m.end()
                col += consumed
                continue
            if text.startswith("<=", pos):
                yield Token("OP_LE", "<=", line, col)
                pos += 2
                col += 2
                continue
            yield Token("OP_LT", "<", line, col)
            pos += 1
            col += 1
            continue
        if ch == ">":
            if text.startswith(">=", pos):
                yield Token("OP_GE", ">=", line, col)
                pos += 2
                col += 2
                continue
            yield Token("OP_GT", ">", line, col)
            pos += 1
            col += 1
            continue
        # multi-char operators starting with ':'
        if ch == ":":
            for prefix, kind in _COLON_OPS:
                if text.startswith(prefix, pos):
                    yield Token(kind, prefix, line, col)
                    pos += len(prefix)
                    col += len(prefix)
                    break
            else:
                yield Token("OP_TYPE", ":", line, col)
                pos += 1
                col += 1
            continue
        # range  ..
        if text.startswith("..", pos):
            yield Token("OP_RANGE", "..", line, col)
            pos += 2
            col += 2
            continue
        # numbers (including a leading minus when next char is a digit)
        m = NUMBER.match(text, pos)
        if m is not None and (ch.isdigit() or (ch == "-" and pos + 1 < n and text[pos + 1].isdigit())):
            yield Token("NUMBER", m.group(0), line, col)
            consumed = m.end() - pos
            pos = m.end()
            col += consumed
            continue
        # strings
        if ch == '"':
            m = STRING.match(text, pos)
            if m is None:
                raise LexError(f"unterminated string at line {line}")
            yield Token("STRING", m.group(0)[1:-1], line, col)
            line, col = _advance(m.group(0), line, col)
            pos = m.end()
            continue
        # identifiers / keywords (with annotation-name extension)
        m = IDENT.match(text, pos)
        if m is not None:
            end = m.end()
            if (
                end < n
                and text[end] == "-"
                and end + 1 < n
                and (text[end + 1].isalnum() or text[end + 1] == "_")
            ):
                ext = ANNOTATION_NAME.match(text, pos)
                if ext is not None:
                    m = ext
            value = m.group(0)
            kind = "KEYWORD" if value in KEYWORDS else "IDENT"
            yield Token(kind, value, line, col)
            consumed = m.end() - pos
            pos = m.end()
            col += consumed
            continue
        # single-char punctuation table
        single = PUNCT.get(ch)
        if single is not None:
            yield Token(single, ch, line, col)
            pos += 1
            col += 1
            continue
        # leftover arithmetic-ish operators (used inside assert-constraint)
        leftover = _SINGLE_OPS.get(ch)
        if leftover is not None:
            yield Token(leftover, ch, line, col)
            pos += 1
            col += 1
            continue
        raise LexError(f"unexpected character {ch!r} at line {line} col {col}")
    yield Token("EOF", "", line, col)


# Order matters: longest prefix first so ``::>`` wins over ``::``.
_COLON_OPS: tuple[tuple[str, str], ...] = (
    ("::>", "OP_SUBSET"),
    ("::", "QNAME_SEP"),
    (":>>", "OP_REDEFINE"),
    (":>", "OP_SPECIALIZE"),
)


_SINGLE_OPS: dict[str, str] = {
    "-": "OP_MINUS",
    "+": "OP_PLUS",
    "/": "OP_SLASH",
    "%": "OP_PERCENT",
}


def _advance(consumed_text: str, line: int, col: int) -> tuple[int, int]:
    """Recompute (line, col) after consuming a multi-line lexeme."""
    for c in consumed_text:
        if c == "\n":
            line += 1
            col = 1
        else:
            col += 1
    return line, col


def is_skip_keyword(value: str) -> bool:
    return value in SKIP_KEYWORDS


def keyword_set() -> Iterable[str]:
    return KEYWORDS
