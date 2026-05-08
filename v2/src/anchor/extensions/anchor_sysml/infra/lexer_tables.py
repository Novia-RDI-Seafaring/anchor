"""Lexer tables: keyword sets, token kinds, regex patterns, punctuation map.

Kept separate from the main scanner so ``lexer.py`` stays focused on the
character loop. Nothing here imports anything that would couple the lexer
to the rest of the package.
"""
from __future__ import annotations

import re

KEYWORDS: frozenset[str] = frozenset(
    {
        "package",
        "part",
        "def",
        "attribute",
        "value",
        "port",
        "in",
        "out",
        "inout",
        "item",
        "interface",
        "connect",
        "to",
        "connection",
        "requirement",
        "subject",
        "assert",
        "constraint",
        "satisfy",
        "by",
        "import",
        "doc",
        "private",
        "public",
        "ref",
        "metadata",
        "perform",
        "action",
        "state",
        "transition",
        "flow",
        "calc",
        "first",
        "then",
        "accept",
        "via",
        "do",
        "entry",
        "exit",
        "when",
        "end",
    }
)

# Constructs we parse-but-skip (warned-once) so that the GfSE corpus parses
# clean even when the file contains constructs outside Phase 1 scope.
SKIP_KEYWORDS: frozenset[str] = frozenset(
    {"action", "state", "transition", "flow", "calc"}
)


TOKEN_KINDS = (
    "KEYWORD",
    "IDENT",
    "QNAME_SEP",       # ::
    "ANGLE_ID",        # <'REQ-42'>
    "STRING",
    "NUMBER",
    "DOC",             # doc /* ... */ payload (without the markers)
    "LBRACE",
    "RBRACE",
    "LPAREN",
    "RPAREN",
    "LBRACK",
    "RBRACK",
    "SEMI",
    "COMMA",
    "DOT",
    "AT",
    "HASH",
    "EQ",              # =
    "OP_TYPE",         # :
    "OP_SPECIALIZE",   # :>
    "OP_REDEFINE",     # :>>
    "OP_SUBSET",       # ::>
    "OP_RANGE",        # ..
    "OP_LE",           # <=
    "OP_GE",           # >=
    "OP_LT",
    "OP_GT",
    "OP_TILDE",        # ~
    "OP_STAR",
    "OP_MINUS",
    "OP_PLUS",
    "OP_SLASH",
    "OP_PERCENT",
    "EOF",
)


LINE_COMMENT = re.compile(r"//[^\n]*")
DOC_COMMENT = re.compile(r"/\*(.*?)\*/", re.DOTALL)
IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
# Annotation-name extension: SysML annotation keys like `@iso15926-uri`
# include hyphens between alphanumeric runs. Tried after IDENT only when an
# IDENT match is followed by `-LETTER/DIGIT/_`.
ANNOTATION_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:-[A-Za-z_0-9]+)+")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
STRING = re.compile(r'"(?:\\.|[^"\\])*"')
ANGLE_ID = re.compile(r"<'([^']+)'>")


PUNCT: dict[str, str] = {
    "{": "LBRACE",
    "}": "RBRACE",
    "(": "LPAREN",
    ")": "RPAREN",
    "[": "LBRACK",
    "]": "RBRACK",
    ";": "SEMI",
    ",": "COMMA",
    ".": "DOT",
    "@": "AT",
    "#": "HASH",
    "=": "EQ",
    "~": "OP_TILDE",
    "*": "OP_STAR",
}


__all__ = [
    "KEYWORDS",
    "SKIP_KEYWORDS",
    "TOKEN_KINDS",
    "LINE_COMMENT",
    "DOC_COMMENT",
    "IDENT",
    "ANNOTATION_NAME",
    "NUMBER",
    "STRING",
    "ANGLE_ID",
    "PUNCT",
]
