"""CLI adapter tests for canvas workspace operations."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from anchor.adapters.cli.main import app


def test_canvas_delete_cli_requires_confirmation_and_removes_workspace(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()

    create = runner.invoke(app, ["canvas", "create", "scratch", "--data-dir", str(data_dir)])
    assert create.exit_code == 0, create.output
    assert (data_dir / "canvases" / "scratch" / "meta.json").is_file()

    refused = runner.invoke(app, ["canvas", "delete", "scratch", "--data-dir", str(data_dir)])
    assert refused.exit_code == 2
    assert (data_dir / "canvases" / "scratch" / "meta.json").is_file()

    deleted = runner.invoke(
        app,
        ["canvas", "delete", "scratch", "--yes", "--data-dir", str(data_dir)],
    )
    assert deleted.exit_code == 0, deleted.output
    assert json.loads(deleted.output) == {"slug": "scratch", "deleted": True}
    assert not (data_dir / "canvases" / "scratch").exists()


def _add(runner, data_dir, slug, node_type, **opts):
    args = ["canvas", "add-node", slug, node_type, "--data-dir", str(data_dir)]
    for k, v in opts.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    return runner.invoke(app, args)


def test_cli_add_node_auto_places_and_returns_position(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r1 = _add(runner, data_dir, "w1", "fact", width=120, height=80)
    assert r1.exit_code == 0, r1.output
    out1 = json.loads(r1.output)
    assert out1["position"] == {"x": 0.0, "y": 0.0}
    r2 = _add(runner, data_dir, "w1", "fact", width=120, height=80)
    out2 = json.loads(r2.output)
    assert out2["position"] != out1["position"]


def test_cli_add_node_warns_on_dead_data_key(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r = runner.invoke(app, [
        "canvas", "add-node", "w1", "fact", "--x", "0", "--y", "0",
        "--data", json.dumps({"body": "nope"}), "--data-dir", str(data_dir),
    ])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert "warning" in out and "body" in out["warning"]


def test_cli_update_node_data_merges(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    add = runner.invoke(app, [
        "canvas", "add-node", "w1", "fact", "--x", "0", "--y", "0",
        "--data", json.dumps({"text": "x", "source_ref": {"page": 1}}),
        "--data-dir", str(data_dir),
    ])
    node_id = json.loads(add.output)["event"]["payload"]["id"]
    upd = runner.invoke(app, [
        "canvas", "update-node", "w1", node_id,
        "--data", json.dumps({"text": "y"}), "--data-dir", str(data_dir),
    ])
    assert upd.exit_code == 0, upd.output
    state = json.loads(upd.output)["state"]
    node = next(n for n in state["nodes"] if n["id"] == node_id)
    assert node["data"]["text"] == "y"
    assert node["data"]["source_ref"] == {"page": 1}


def test_cli_node_types_command(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    r = runner.invoke(app, ["canvas", "node-types", "fact", "--data-dir", str(data_dir)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out[0]["name"] == "fact" and out[0]["body_field"] == "text"


def test_cli_reference_create_list_attach_roundtrip(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    _add(runner, data_dir, "w1", "fact", x=0, y=0)
    # The fact node id is auto-assigned; read it from state.
    state = json.loads(
        runner.invoke(app, ["canvas", "state", "w1", "--data-dir", str(data_dir)]).output
    )
    node_id = state["nodes"][0]["id"]

    created = runner.invoke(app, [
        "canvas", "reference", "create", "w1",
        "--source-ref", json.dumps({"slug": "d", "page": 3, "bbox": [1, 2, 3, 4]}),
        "--label", "Inlet pressure",
        "--data-dir", str(data_dir),
    ])
    assert created.exit_code == 0, created.output
    ref = json.loads(created.output)
    assert ref["id"]
    assert ref["created_by"] == "human"  # CLI default

    listed = runner.invoke(app, ["canvas", "reference", "list", "w1", "--data-dir", str(data_dir)])
    assert listed.exit_code == 0, listed.output
    assert [r["id"] for r in json.loads(listed.output)] == [ref["id"]]

    attached = runner.invoke(app, [
        "canvas", "reference", "attach", "w1", ref["id"],
        "--node", node_id, "--data-dir", str(data_dir),
    ])
    assert attached.exit_code == 0, attached.output
    out = json.loads(attached.output)
    assert out["event"]["type"] == "ReferenceAttached"
    node = next(n for n in out["state"]["nodes"] if n["id"] == node_id)
    assert node["data"]["reference_id"] == ref["id"]
    assert node["data"]["source_ref"]["slug"] == "d"


def test_cli_reference_remove_and_update_roundtrip(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    created = runner.invoke(app, [
        "canvas", "reference", "create", "w1",
        "--source-ref", json.dumps({"slug": "d", "page": 1}),
        "--label", "old", "--data-dir", str(data_dir),
    ])
    ref = json.loads(created.output)

    updated = runner.invoke(app, [
        "canvas", "reference", "update", "w1", ref["id"],
        "--label", "new", "--data-dir", str(data_dir),
    ])
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["event"]["type"] == "ReferenceUpdated"
    listed = runner.invoke(app, ["canvas", "reference", "list", "w1", "--data-dir", str(data_dir)])
    assert json.loads(listed.output)[0]["label"] == "new"

    removed = runner.invoke(app, [
        "canvas", "reference", "remove", "w1", ref["id"], "--data-dir", str(data_dir),
    ])
    assert removed.exit_code == 0, removed.output
    assert json.loads(removed.output)["event"]["type"] == "ReferenceRemoved"
    listed2 = runner.invoke(app, ["canvas", "reference", "list", "w1", "--data-dir", str(data_dir)])
    assert json.loads(listed2.output) == []


def test_cli_reference_remove_unknown_errors(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r = runner.invoke(app, [
        "canvas", "reference", "remove", "w1", "ghost", "--data-dir", str(data_dir),
    ])
    assert r.exit_code == 2


def test_cli_reference_create_rejects_malformed(tmp_path):
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r = runner.invoke(app, [
        "canvas", "reference", "create", "w1",
        "--source-ref", json.dumps({"page": 3}),
        "--data-dir", str(data_dir),
    ])
    assert r.exit_code == 2
