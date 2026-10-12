from anchor.infra.activity import ActivityLog


def test_records_and_reads_back_in_order(tmp_path):
    log = ActivityLog(tmp_path)
    log.record(kind="http", name="GET /api/intents", ms=1.2)
    log.record(kind="mcp", name="intent_act", ms=20.0, intent="i1", ts=5.0)
    entries = log.read()
    assert [e["kind"] for e in entries] == ["http", "mcp"]
    assert entries[0]["ts"] > 1e9 and entries[1]["ts"] == 5.0
    assert entries[1]["intent"] == "i1"


def test_since_and_limit(tmp_path):
    log = ActivityLog(tmp_path)
    for i in range(5):
        log.record(kind="http", name=f"n{i}", ms=0, ts=100.0 + i)
    assert [e["name"] for e in log.read(since=103.0)] == ["n3", "n4"]
    assert [e["name"] for e in log.read(limit=2)] == ["n3", "n4"]


def test_missing_or_broken_lines_do_not_raise(tmp_path):
    log = ActivityLog(tmp_path)
    assert log.read() == []
    (tmp_path / "activity.jsonl").write_text('{"ts": 1, "kind": "http"}\nnot json\n\n')
    assert len(log.read()) == 1
