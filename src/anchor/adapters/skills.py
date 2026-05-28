"""Compose the agent-facing SKILL.md from the bundled skill files.

The previous architecture stored the SKILL.md verbatim as a Python
string constant in ``install.py``. That worked for one file but
didn't scale: every extension needs its own section, the content
should be diffable, and the same source has to feed several agent
surfaces (the installed SKILL.md, the MCP server's ``instructions``
field, and the ``anchor://help`` resource).

This module is the single source of truth for that text. It walks
the ``anchor.skills`` package, concatenates the core skill with each
enabled extension's skill snippet, and returns one rendered string.
Adapters (``cli/install.py``, the MCP stdio server) pull from here.

The skill files themselves live under ``src/anchor/skills/`` so they
ship inside the wheel as package data; no separate packaging dance.
"""
from __future__ import annotations

from importlib.resources import files
from typing import Iterable

#: Bundled extensions whose skill files ship in this wheel. Keep the
#: order stable — it determines the section ordering in the rendered
#: SKILL.md. Third-party extensions register through the OIP manifest
#: later; this list captures only what we ship in-tree today.
_BUNDLED_EXTENSIONS: tuple[str, ...] = (
    "anchor_pdfs",
)


def _read(*parts: str) -> str:
    """Read a packaged skill file or return an empty string if missing.

    Returning empty rather than raising keeps the composer resilient
    against extensions that don't ship a skill snippet — they're just
    absent from the rendered output instead of crashing the install.
    """
    resource = files("anchor.skills").joinpath(*parts)
    if not resource.is_file():
        return ""
    return resource.read_text(encoding="utf-8")


def compose_skill_md(extensions: Iterable[str] | None = None) -> str:
    """Build the agent-facing SKILL.md from core + enabled extensions.

    Parameters
    ----------
    extensions:
        Iterable of extension package names whose ``skill.md`` snippets
        should be appended after the core. ``None`` means "all bundled
        extensions, in their declared order".

    Returns
    -------
    The fully rendered SKILL.md text. Empty extensions are skipped
    silently so callers can pass a wide set without worrying about
    coverage.
    """
    selected = tuple(extensions) if extensions is not None else _BUNDLED_EXTENSIONS

    sections: list[str] = []

    core = _read("core.md")
    if core:
        sections.append(core.rstrip())

    canvas = _read("canvas.md")
    if canvas:
        sections.append(canvas.rstrip())

    for ext_name in selected:
        snippet = _read("extensions", ext_name, "skill.md")
        if snippet:
            sections.append(snippet.rstrip())

    # Single blank line between sections; one trailing newline so the
    # file ends cleanly on disk.
    return "\n\n".join(sections) + "\n"


def list_bundled_extensions() -> tuple[str, ...]:
    """Expose the bundled extension set to callers that want to verify
    what will be composed (CLI ``anchor doctor`` is a likely caller).
    """
    return _BUNDLED_EXTENSIONS
