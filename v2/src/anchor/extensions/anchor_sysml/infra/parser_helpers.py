"""Token cursor + low-level reader helpers used across the parser modules.

Kept separate from the grammar files so the recursive-descent code reads as
"what comes next" instead of being interleaved with skip-and-recover logic.
"""
from __future__ import annotations

from anchor.extensions.anchor_sysml.core.schemas import Diagnostic, SourceRef
from anchor.extensions.anchor_sysml.infra.lexer import Token


# ── Cursor ───────────────────────────────────────────────────────────────


class Cursor:
    """A small token cursor with peek/eat/check helpers."""

    def __init__(self, tokens: list[Token], filename: str | None) -> None:
        self.tokens = tokens
        self.pos = 0
        self.filename = filename
        self.diagnostics: list[Diagnostic] = []
        self._skip_warned: set[str] = set()

    # peek/check ---------------------------------------------------------

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def at(self, kind: str, value: str | None = None) -> bool:
        t = self.peek()
        if t.kind != kind:
            return False
        if value is not None and t.value != value:
            return False
        return True

    def at_keyword(self, *values: str) -> bool:
        t = self.peek()
        return t.kind == "KEYWORD" and t.value in values

    def eof(self) -> bool:
        return self.peek().kind == "EOF"

    # consume ------------------------------------------------------------

    def eat(self) -> Token:
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, kind: str, value: str | None = None) -> Token:
        t = self.peek()
        if t.kind != kind or (value is not None and t.value != value):
            raise ParseError(t, f"expected {kind}{f' {value!r}' if value else ''}, got {t.kind} {t.value!r}")
        return self.eat()

    # diagnostics --------------------------------------------------------

    def warn(self, t: Token, message: str, *, level: str = "warning") -> None:
        self.diagnostics.append(
            Diagnostic(level=level, line=t.line, col=t.col, message=message)
        )

    def warn_skip(self, kw: str, t: Token) -> None:
        if kw not in self._skip_warned:
            self._skip_warned.add(kw)
            self.warn(t, f"SysML construct '{kw}' is not supported in Phase 1; skipped.")

    def src(self, t: Token) -> SourceRef:
        return SourceRef(file=self.filename, line=t.line, col=t.col)


class ParseError(Exception):
    def __init__(self, token: Token, message: str) -> None:
        super().__init__(f"{message} (line {token.line}, col {token.col})")
        self.token = token


# ── Reserved name set (shared between parsers) ───────────────────────────

RESERVED_NAMES: frozenset[str] = frozenset(
    {"package", "part", "def", "requirement", "interface", "connect", "to",
     "satisfy", "by", "import", "doc", "subject", "assert", "constraint",
     "metadata"}
)


# ── Skipping helpers ─────────────────────────────────────────────────────


def skip_to_semi(cur: Cursor) -> None:
    """Skip tokens until we reach a semicolon (consumed) or a brace boundary."""
    depth = 0
    while not cur.eof():
        t = cur.peek()
        if depth == 0 and t.kind == "SEMI":
            cur.eat()
            return
        if depth == 0 and t.kind == "RBRACE":
            return
        if t.kind == "LBRACE":
            depth += 1
        elif t.kind == "RBRACE":
            depth -= 1
        cur.eat()


def skip_braces(cur: Cursor) -> None:
    """Consume a balanced ``{ … }`` group starting at the current token."""
    if not cur.at("LBRACE"):
        return
    depth = 0
    while not cur.eof():
        t = cur.peek()
        if t.kind == "LBRACE":
            depth += 1
        elif t.kind == "RBRACE":
            depth -= 1
            cur.eat()
            if depth == 0:
                return
            continue
        cur.eat()


def skip_brackets(cur: Cursor) -> None:
    if not cur.at("LBRACK"):
        return
    depth = 0
    while not cur.eof():
        t = cur.peek()
        if t.kind == "LBRACK":
            depth += 1
        elif t.kind == "RBRACK":
            depth -= 1
            cur.eat()
            if depth == 0:
                return
            continue
        cur.eat()


def skip_construct(cur: Cursor) -> None:
    """Skip an unsupported statement: read up to ``;`` or balanced ``{…}``."""
    while not cur.eof():
        t = cur.peek()
        if t.kind == "SEMI":
            cur.eat()
            return
        if t.kind == "LBRACE":
            skip_braces(cur)
            return
        if t.kind == "RBRACE":
            return
        cur.eat()


def skip_to_balanced(cur: Cursor) -> None:
    """Recovery: skip until brace depth returns to zero."""
    depth = 0
    while not cur.eof():
        t = cur.peek()
        if t.kind == "LBRACE":
            depth += 1
        elif t.kind == "RBRACE":
            depth -= 1
            cur.eat()
            if depth <= 0:
                return
            continue
        cur.eat()


# ── Token-level readers ──────────────────────────────────────────────────


def expect_ident_like(cur: Cursor, what: str) -> Token:
    """Identifier or contextual keyword used as a name."""
    t = cur.peek()
    if t.kind == "IDENT" or (t.kind == "KEYWORD" and t.value not in RESERVED_NAMES):
        return cur.eat()
    raise ParseError(t, f"expected {what}, got {t.kind} {t.value!r}")


def parse_qname(cur: Cursor) -> str:
    """Read a qualified name like ``Foo::Bar::baz``."""
    parts: list[str] = [expect_ident_like(cur, "name").value]
    while cur.at("QNAME_SEP") or cur.at("DOT"):
        sep = cur.eat()
        if sep.kind == "QNAME_SEP" and cur.at("OP_STAR"):
            cur.eat()
            parts.append("*")
            break
        parts.append(expect_ident_like(cur, "name segment").value)
    return "::".join(parts)


def parse_import_path(cur: Cursor) -> str:
    """Imports may end with ``::*`` — keep as a single qualified path."""
    return parse_qname(cur)


def read_dotted_path(cur: Cursor) -> str:
    """Read a path of the form ``a.b.c`` or ``a::b::c.d`` keeping separators."""
    parts: list[str] = [expect_ident_like(cur, "path segment").value]
    while True:
        if cur.at("DOT"):
            cur.eat()
            parts.append("." + expect_ident_like(cur, "path segment").value)
            continue
        if cur.at("QNAME_SEP"):
            cur.eat()
            parts.append("::" + expect_ident_like(cur, "path segment").value)
            continue
        break
    return "".join(parts)


def read_subject(cur: Cursor) -> str:
    """Read the textual content of a `subject …;` clause as a flat string."""
    parts: list[str] = []
    while not cur.eof() and not cur.at("SEMI"):
        t = cur.peek()
        if t.kind in ("RBRACE", "LBRACE"):
            break
        parts.append(t.value if t.kind != "QNAME_SEP" else "::")
        cur.eat()
    if cur.at("SEMI"):
        cur.eat()
    return " ".join(parts).strip()


def read_constraint_block(cur: Cursor) -> str:
    """An assert constraint may be followed by a ``{ expr }`` body or a
    semicolon-terminated expression."""
    if cur.at("LBRACE"):
        cur.eat()
        depth = 1
        chunks: list[str] = []
        while not cur.eof() and depth > 0:
            t = cur.eat()
            if t.kind == "LBRACE":
                depth += 1
                chunks.append("{")
            elif t.kind == "RBRACE":
                depth -= 1
                if depth == 0:
                    break
                chunks.append("}")
            else:
                chunks.append(t.value if t.kind != "QNAME_SEP" else "::")
        return " ".join(chunks).strip()
    parts: list[str] = []
    while not cur.eof() and not cur.at("SEMI"):
        t = cur.eat()
        if t.kind == "RBRACE":
            break
        parts.append(t.value if t.kind != "QNAME_SEP" else "::")
    if cur.at("SEMI"):
        cur.eat()
    return " ".join(parts).strip()


def read_literal_until_semi(cur: Cursor) -> str:
    """Read tokens forming a literal until ``;`` / closing brace / comma;
    do NOT consume the terminator."""
    parts: list[str] = []
    while (
        not cur.eof()
        and not cur.at("SEMI")
        and not cur.at("RBRACE")
        and not cur.at("COMMA")
    ):
        t = cur.peek()
        if t.kind == "KEYWORD" and t.value in RESERVED_NAMES:
            break
        parts.append(t.value)
        cur.eat()
    return " ".join(parts).strip()


__all__ = [
    "Cursor", "ParseError", "RESERVED_NAMES",
    "skip_to_semi", "skip_braces", "skip_brackets", "skip_construct", "skip_to_balanced",
    "expect_ident_like", "parse_qname", "parse_import_path",
    "read_dotted_path", "read_subject", "read_constraint_block", "read_literal_until_semi",
]
