"""The frontend fixture is the actual backend producer payload, not a second schema."""
import json
from pathlib import Path

from tests.fixtures.document_page_geometry import produce, write_pdf


async def test_frontend_geometry_fixture_matches_silver_and_gold_map(tmp_path):
    pdf = tmp_path / "geometry.pdf"
    write_pdf(pdf)
    fixture = Path(__file__).parents[3] / "web/src/lib/fixtures/documentPageGeometry.json"
    assert await produce(pdf) == json.loads(fixture.read_text(encoding="utf-8"))
