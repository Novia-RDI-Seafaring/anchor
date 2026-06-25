"""`anchor intents` / `anchor intent resolve` -- the shell surface of the agent
intent queue (issue #148). Reads the same durable project store the server
writes, so a CLI can drain what the UI enqueued."""
from __future__ import annotations

import asyncio
import json

from typer.testing import CliRunner

from anchor.adapters.cli.main import app
from anchor.core.intents.intent import Intent
from anchor.infra.stores.fs_intent_store import FsIntentStore

runner = CliRunner()


def _seed(data_dir, **over):
    rec = {"kind": "drop_to_ingest", "origin_canvas_id": "cv", "created_at": 1.0}
    rec.update(over)
    intent = Intent(**rec)
    asyncio.run(FsIntentStore(data_dir).add(intent))
    return intent


def test_intents_lists_pending(tmp_path):
    seeded = _seed(tmp_path, payload={"slug": "pump"})
    result = runner.invoke(app, ["intents", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert [i["id"] for i in body["intents"]] == [seeded.id]
    assert body["intents"][0]["payload"]["slug"] == "pump"


def test_intents_empty(tmp_path):
    result = runner.invoke(app, ["intents", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"intents": []}


def test_intents_canvas_filter(tmp_path):
    _seed(tmp_path, origin_canvas_id="a")
    assert (
        json.loads(
            runner.invoke(
                app, ["intents", "--canvas", "z", "--data-dir", str(tmp_path)]
            ).output
        )
        == {"intents": []}
    )
    one = json.loads(
        runner.invoke(
            app, ["intents", "--canvas", "a", "--data-dir", str(tmp_path)]
        ).output
    )
    assert len(one["intents"]) == 1


def test_intent_resolve(tmp_path):
    seeded = _seed(tmp_path)
    result = runner.invoke(
        app,
        [
            "intent", "resolve", seeded.id,
            "--result", '{"produced_slug": "pump"}',
            "--data-dir", str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["resolved"]["status"] == "resolved"
    assert out["resolved"]["result"] == {"produced_slug": "pump"}
    # No longer pending.
    listed = json.loads(runner.invoke(app, ["intents", "--data-dir", str(tmp_path)]).output)
    assert listed == {"intents": []}


def test_intent_resolve_missing_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["intent", "resolve", "ghost", "--data-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert json.loads(result.output)["error"] == "not_found"


def test_intent_next_peeks_oldest(tmp_path):
    seeded = _seed(tmp_path)
    out = json.loads(
        runner.invoke(app, ["intent", "next", "--data-dir", str(tmp_path)]).output
    )
    assert out["intent"]["id"] == seeded.id
