import json
from pathlib import Path

from anchor.adapters.schema_export import export_core_wire_schema


def test_web_core_schema_snapshot_matches_python_export():
    root = Path(__file__).resolve().parents[2]
    snapshot_path = root / "web" / "src" / "generated" / "anchor-core.schema.json"

    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == export_core_wire_schema()
