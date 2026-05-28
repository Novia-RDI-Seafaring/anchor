"""Compose the agent-facing SKILL.md from the bundled skill files
and from third-party OIP producers' ``agent`` blocks.

The previous architecture stored the SKILL.md verbatim as a Python
string constant in ``install.py``. That worked for one file but
didn't scale: every extension needs its own section, the content
should be diffable, and the same source has to feed several agent
surfaces (the installed SKILL.md, the MCP server's ``instructions``
field, and the ``anchor://help`` resource).

This module is the single source of truth for that text. It walks:

1. The ``anchor.skills`` package data (core + canvas + bundled
   extensions that ship in this wheel).
2. Optionally, third-party OIP producer manifests registered via
   ``anchor extensions add`` or dropped into the OIP discovery
   directories — each may declare an ``agent`` block per OIP 0.2.

Bundled and third-party sections are concatenated in a stable
order so the rendered output is deterministic across installs.
"""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Iterable

#: Bundled extensions whose skill files ship in this wheel. Keep the
#: order stable — it determines the section ordering in the rendered
#: SKILL.md. Third-party extensions register through OIP manifests
#: and are appended after this set.
_BUNDLED_EXTENSIONS: tuple[str, ...] = (
    "anchor_pdfs",
)


def _read_packaged(*parts: str) -> str:
    """Read a packaged skill file or return an empty string if missing.

    Returning empty rather than raising keeps the composer resilient
    against extensions that don't ship a skill snippet — they're just
    absent from the rendered output instead of crashing the install.
    """
    resource = files("anchor.skills").joinpath(*parts)
    if not resource.is_file():
        return ""
    return resource.read_text(encoding="utf-8")


def _read_third_party_skill(manifest_path: Path) -> str:
    """Resolve a third-party producer's ``agent`` block to skill text.

    OIP 0.2 introduces an optional ``agent`` block on ``manifest.json``
    with either ``skill_path`` (relative to the manifest directory) or
    ``skill`` (inline markdown). This reads the JSON, follows whichever
    of the two is set, and returns the text. Returns empty string for
    every "nothing to contribute" case so callers can pass the full
    set of discovered manifests without filtering first.
    """
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Malformed manifests are reported elsewhere (``anchor
        # extensions list`` shows the parse error); the composer just
        # skips them so a single broken file doesn't break the whole
        # SKILL.md.
        return ""

    agent = manifest.get("agent")
    if not isinstance(agent, dict):
        return ""

    # Inline content wins when both are set, even though the OIP
    # schema's oneOf forbids it. Defensive: if a producer somehow
    # slips both past validation, the inline one is the explicit
    # author intent.
    inline = agent.get("skill")
    if isinstance(inline, str) and inline.strip():
        return inline

    path_field = agent.get("skill_path")
    if isinstance(path_field, str) and path_field:
        # OIP spec: skill_path is relative to the manifest's directory.
        skill_path = (manifest_path.parent / path_field).resolve()
        # Containment: the resolved path must stay inside the manifest
        # directory tree. A producer pointing at /etc/passwd or
        # ../../../secrets is rejected silently — defence in depth.
        try:
            skill_path.relative_to(manifest_path.parent.resolve())
        except ValueError:
            return ""
        if not skill_path.is_file():
            return ""
        try:
            return skill_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    return ""


def compose_skill_md(
    extensions: Iterable[str] | None = None,
    third_party_manifests: Iterable[Path] | None = None,
) -> str:
    """Build the agent-facing SKILL.md from core + extensions.

    Parameters
    ----------
    extensions:
        Iterable of bundled extension package names whose ``skill.md``
        snippets should be appended after the core. ``None`` means
        "all bundled extensions, in their declared order".
    third_party_manifests:
        Iterable of paths to OIP ``manifest.json`` files registered
        outside this wheel. Each is read for its ``agent`` block and
        contributes the resolved skill text to the rendered output.
        Manifests without an ``agent`` block are silently skipped.

    Returns
    -------
    The fully rendered SKILL.md text. Empty contributors are skipped
    silently so callers can pass a wide set without worrying about
    coverage.

    Ordering
    --------
    ``core → canvas → bundled extensions → third-party producers``.
    The first three are stable across runs; third-party order is the
    iteration order of the caller's iterable, so callers wanting
    determinism should pass a sorted list.
    """
    selected = tuple(extensions) if extensions is not None else _BUNDLED_EXTENSIONS
    third_party = tuple(third_party_manifests) if third_party_manifests is not None else ()

    sections: list[str] = []

    core = _read_packaged("core.md")
    if core:
        sections.append(core.rstrip())

    canvas = _read_packaged("canvas.md")
    if canvas:
        sections.append(canvas.rstrip())

    for ext_name in selected:
        snippet = _read_packaged("extensions", ext_name, "skill.md")
        if snippet:
            sections.append(snippet.rstrip())

    for manifest_path in third_party:
        snippet = _read_third_party_skill(Path(manifest_path))
        if snippet.strip():
            sections.append(snippet.rstrip())

    # Single blank line between sections; one trailing newline so the
    # file ends cleanly on disk.
    return "\n\n".join(sections) + "\n"


def list_bundled_extensions() -> tuple[str, ...]:
    """Expose the bundled extension set to callers that want to verify
    what will be composed (CLI ``anchor doctor`` is a likely caller).
    """
    return _BUNDLED_EXTENSIONS


def _xdg_config_home() -> Path:
    """Return ``$XDG_CONFIG_HOME`` with the standard fallback."""
    import os
    raw = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".config"


def discover_third_party_manifests(
    data_dir: Path | None = None,
) -> list[Path]:
    """Find every OIP producer manifest registered outside this wheel.

    OIP's discovery convention (SPEC.md §7) walks two locations:

    1. System-wide: ``$XDG_CONFIG_HOME/oip/producers.d/*.json``
    2. Per-data-dir: ``<data-dir>/.oip/producers.d/*.json`` (project-
       scoped; only meaningful when a caller knows which data dir is
       active).

    Returns paths in a stable sorted order so the composed SKILL.md is
    deterministic across runs. Missing directories are silently
    skipped — discovery is opportunistic.

    The composer doesn't validate the manifests it discovers; that's
    the job of ``anchor extensions list`` (which reports parse errors)
    and the OIP validator. The composer just ignores anything it
    can't read.
    """
    found: list[Path] = []

    system_dir = _xdg_config_home() / "oip" / "producers.d"
    if system_dir.is_dir():
        found.extend(sorted(system_dir.glob("*.json")))

    if data_dir is not None:
        project_dir = Path(data_dir) / ".oip" / "producers.d"
        if project_dir.is_dir():
            found.extend(sorted(project_dir.glob("*.json")))

    return found
