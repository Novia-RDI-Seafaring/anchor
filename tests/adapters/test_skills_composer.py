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


def test_core_skill_explains_tool_installation():
    out = compose_skill_md()
    assert "uv tool install anchor-kb" in out
    assert "pipx install anchor-kb" in out
    assert "`anchor install <harness>` registers" in out
    assert "ANCHOR_OPENAI_API_KEY" in out


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


# ── Third-party manifest reading (OIP 0.2 `agent` block) ─────────────


import json  # noqa: E402  (intentional — block-scoped to third-party tests)

from anchor.adapters.skills import discover_third_party_manifests  # noqa: E402


def _write_manifest(dir_: object, **agent_overrides):  # type: ignore[no-untyped-def]
    """Helper: write a minimal OIP 0.2 manifest.json with an agent block."""
    from pathlib import Path

    path = Path(dir_) / "manifest.json"
    body = {
        "oip_version": "0.2",
        "producer": {"name": "test", "version": "0.1.0"},
        "data_dir": str(dir_),
        "produces": {
            "source_kinds": [],
            "region_kinds": [],
            "source_ref_kinds": [],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "noop",
            "tools_namespace": "test",
        },
    }
    if agent_overrides:
        body["agent"] = agent_overrides
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_third_party_inline_skill_appended(tmp_path):
    """A manifest with inline ``agent.skill`` contributes its text to
    the composed output, appended after the bundled sections."""
    manifest = _write_manifest(tmp_path, skill="## acme — what it does\n\nUse this when X.\n")
    out = compose_skill_md(third_party_manifests=[manifest])
    assert "## acme — what it does" in out
    # The third-party section comes after the bundled extension.
    assert out.index("anchor_pdfs") < out.index("acme")


def test_third_party_skill_path_resolved(tmp_path):
    """A manifest with ``agent.skill_path`` reads the file relative to
    the manifest directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "skill.md").write_text("## acme\n\nA third party.\n", encoding="utf-8")
    manifest = _write_manifest(tmp_path, skill_path="skills/skill.md")
    out = compose_skill_md(third_party_manifests=[manifest])
    assert "A third party." in out


def test_third_party_missing_agent_block_skipped(tmp_path):
    """No ``agent`` field at all → contributes nothing, no crash."""
    manifest = _write_manifest(tmp_path)  # no agent overrides
    out = compose_skill_md(third_party_manifests=[manifest])
    # Bundled content still there, no third-party text appended.
    assert "anchor_pdfs" in out
    assert "## acme" not in out


def test_third_party_missing_skill_file_skipped(tmp_path):
    """Manifest points at a file that doesn't exist → silently skipped."""
    manifest = _write_manifest(tmp_path, skill_path="skills/nonexistent.md")
    out = compose_skill_md(third_party_manifests=[manifest])
    assert "## acme" not in out


def test_third_party_skill_path_traversal_rejected(tmp_path):
    """A ``skill_path`` that escapes the manifest directory is silently
    refused. The composer never reads files outside the producer's
    own tree."""
    outside = tmp_path.parent / "outside-secret.md"
    outside.write_text("SECRET\n", encoding="utf-8")
    manifest = _write_manifest(tmp_path, skill_path="../outside-secret.md")
    out = compose_skill_md(third_party_manifests=[manifest])
    assert "SECRET" not in out


def test_third_party_malformed_manifest_skipped(tmp_path):
    """Manifest that isn't valid JSON → silently skipped, not a crash."""
    bad = tmp_path / "manifest.json"
    bad.write_text("not json {[", encoding="utf-8")
    out = compose_skill_md(third_party_manifests=[bad])
    # Bundled content still composed; bad manifest contributed nothing.
    assert "anchor_pdfs" in out


def test_third_party_inline_wins_over_path_when_both(tmp_path):
    """Defence-in-depth: even though the OIP oneOf forbids it, if both
    skill and skill_path slip past validation, inline wins as the
    explicit author intent."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "skill.md").write_text("FROM FILE\n", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        skill="FROM INLINE\n",
        skill_path="skills/skill.md",
    )
    out = compose_skill_md(third_party_manifests=[manifest])
    assert "FROM INLINE" in out
    assert "FROM FILE" not in out


# ── discover_third_party_manifests ─────────────────────────────────────


def test_discover_finds_project_manifests(tmp_path, monkeypatch):
    """Discovery walks the data-dir's ``.oip/producers.d/`` directory."""
    project = tmp_path / ".oip" / "producers.d"
    project.mkdir(parents=True)
    (project / "alpha.json").write_text("{}")
    (project / "beta.json").write_text("{}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nope"))  # ensure no system hits
    paths = discover_third_party_manifests(data_dir=tmp_path)
    names = sorted(p.name for p in paths)
    assert names == ["alpha.json", "beta.json"]


def test_discover_finds_system_manifests(tmp_path, monkeypatch):
    """Discovery walks ``$XDG_CONFIG_HOME/oip/producers.d/``."""
    sys_dir = tmp_path / "config" / "oip" / "producers.d"
    sys_dir.mkdir(parents=True)
    (sys_dir / "shared.json").write_text("{}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    paths = discover_third_party_manifests(data_dir=None)
    assert [p.name for p in paths] == ["shared.json"]


def test_discover_missing_dirs_yields_empty(tmp_path, monkeypatch):
    """Both locations absent → empty list, not an error."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    paths = discover_third_party_manifests(data_dir=tmp_path / "no-such-data-dir")
    assert paths == []
