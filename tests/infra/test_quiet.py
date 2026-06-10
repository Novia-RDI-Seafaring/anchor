"""Startup quieting keeps third-party noise out of machine-readable output."""
from __future__ import annotations

import logging

from anchor.infra import quiet


def test_quiets_huggingface_and_docling(monkeypatch):
    monkeypatch.delenv("ANCHOR_LOG_LEVEL", raising=False)
    monkeypatch.setattr(quiet, "_QUIETED", False)
    logging.getLogger("huggingface_hub").setLevel(logging.INFO)
    logging.getLogger("transformers").setLevel(logging.INFO)
    logging.getLogger("docling").setLevel(logging.INFO)

    quiet.quiet_dependency_logs()

    assert logging.getLogger("huggingface_hub").level == logging.ERROR
    assert logging.getLogger("transformers").level == logging.ERROR
    assert logging.getLogger("docling").level == logging.WARNING


def test_debug_opts_out(monkeypatch):
    monkeypatch.setenv("ANCHOR_LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(quiet, "_QUIETED", False)
    logging.getLogger("huggingface_hub").setLevel(logging.INFO)

    quiet.quiet_dependency_logs()

    assert logging.getLogger("huggingface_hub").level == logging.INFO  # untouched
