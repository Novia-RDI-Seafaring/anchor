"""Composer tests — verifies the rules that keep the agent text honest.

The composer should:
- Return a string that includes the core skill, canvas tools, and each
  enabled extension's snippet, in declared order.
- Tolerate missing files (skip them rather than crashing).
- Produce stable output regardless of dict ordering.
- Carry the YAML frontmatter at the top (Claude Code requires it).
"""
from __future__ import annotations

from anchor.adapters.skills import compose_skill_md, list_bundled_extensions


def test_returns_non_empty_skill_md():
    out = compose_skill_md()
    assert out
    assert out.endswith("\n")


def test_starts_with_yaml_frontmatter():
    out = compose_skill_md()
    lines = out.splitlines()
    assert lines[0] == "---"
    # The closing fence is somewhere in the first 30 lines (description
    # is multi-line YAML).
    assert "---" in lines[1:30]


def test_includes_core_skill_section():
    out = compose_skill_md()
    # The core file ships a "When to use" section; the composer must
    # include it so the agent has criteria for invoking ANCHOR.
    assert "When to use" in out


def test_includes_canvas_section():
    out = compose_skill_md()
    # canvas.md contributes the workspace + node tool reference.
    assert "canvas_create_workspace" in out
    assert "canvas_add_node" in out


def test_includes_bundled_extensions_by_default():
    out = compose_skill_md()
    for ext in list_bundled_extensions():
        # Each bundled extension's skill.md has a heading containing
        # its package name (e.g. "## `anchor_pdfs`").
        assert ext in out, f"{ext} missing from composed output"


def test_empty_extension_list_still_returns_core():
    out = compose_skill_md(extensions=())
    assert "When to use" in out
    assert "anchor_pdfs" not in out


def test_unknown_extension_silently_skipped():
    """A non-existent extension name should not raise — the composer
    just skips it, so callers can pass an aspirational list without
    worrying about coverage."""
    out = compose_skill_md(extensions=("anchor_pdfs", "anchor_nonexistent"))
    assert "anchor_pdfs" in out
    # No crash, no traceback, no placeholder.
    assert "anchor_nonexistent" not in out


def test_deterministic_output():
    """Two calls return identical bytes; the composer has no side
    effects and reads from the same package data each time."""
    assert compose_skill_md() == compose_skill_md()
