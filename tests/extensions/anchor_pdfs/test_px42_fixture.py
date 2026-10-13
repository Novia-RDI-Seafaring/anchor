"""The maintainer-supplied synthetic document is preserved byte-for-byte."""
import hashlib

import pymupdf

from tests.fixtures.documents.px42 import PDF, SHA256


def test_px42_fixture_checksum_and_four_original_pages():
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA256
    with pymupdf.open(PDF) as document:
        assert len(document) == 4
        assert "original author-created material" in document[0].get_text()
        assert "600 kPa (6 bar)" in document[1].get_text()
