"""Ingest output should read as ANCHOR working, not a wall of docling/OCR logs.

A user (and an agent) misread the docling + RapidOCR INFO chatter as the tool
doing manual OCR. `_quiet_dependency_logs` pins those loggers above INFO by
default, and leaves them alone under ANCHOR_LOG_LEVEL=DEBUG.
"""
from __future__ import annotations

import logging

from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx


def test_quiets_docling_and_rapidocr_by_default(monkeypatch):
    monkeypatch.delenv("ANCHOR_LOG_LEVEL", raising=False)
    monkeypatch.setitem(dx._STATE, "quieted", False)
    logging.getLogger("docling").setLevel(logging.INFO)
    logging.getLogger("RapidOCR").setLevel(logging.INFO)
    logging.getLogger("docling.models.stages.ocr.rapid_ocr_model").setLevel(logging.INFO)

    dx._quiet_dependency_logs()

    assert logging.getLogger("docling").level == logging.WARNING
    assert logging.getLogger("RapidOCR").level == logging.ERROR
    # The "empty result" warning logger is pushed to ERROR specifically.
    assert (
        logging.getLogger("docling.models.stages.ocr.rapid_ocr_model").level == logging.ERROR
    )


def test_debug_keeps_full_log_stream(monkeypatch):
    monkeypatch.setenv("ANCHOR_LOG_LEVEL", "DEBUG")
    monkeypatch.setitem(dx._STATE, "quieted", False)
    logging.getLogger("docling").setLevel(logging.INFO)

    dx._quiet_dependency_logs()

    assert logging.getLogger("docling").level == logging.INFO  # untouched
