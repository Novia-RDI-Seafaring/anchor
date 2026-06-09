"""Silence noisy third-party output so command output stays machine-readable.

The HuggingFace stack (sentence-transformers loads the local ``bge`` embedder
through it) prints an "unauthenticated requests to the HF Hub" warning and a
"Loading weights" progress bar, and docling logs INFO chatter. Those leak into
the output of ``anchor search`` / ``anchor embed`` / ``anchor ingest`` and make a
strict parser choke. Call :func:`quiet_dependency_logs` once at process startup
(CLI and server) to keep output clean. Set ``ANCHOR_LOG_LEVEL=DEBUG`` to keep the
full stream.

This intentionally does NOT import the heavy OCR stack — the docling extractor
installs the RapidOCR-specific filter on its own code path, where RapidOCR is
loaded anyway, so a plain ``anchor version`` never pays that import cost.
"""
from __future__ import annotations

import logging
import os

_QUIETED = False


def quiet_dependency_logs() -> None:
    """Quiet HuggingFace + docling log/progress noise. Idempotent; DEBUG opts out."""
    global _QUIETED
    if _QUIETED or os.environ.get("ANCHOR_LOG_LEVEL", "").upper() == "DEBUG":
        return

    # HuggingFace / transformers / sentence-transformers (embedder load). These
    # env vars are read at *import* time and survive a later re-import, which a
    # logger level does not — the libs reset their own logger when imported.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    # The "unauthenticated requests to the HF Hub" notice is a warnings.warn.
    import warnings

    warnings.filterwarnings("ignore", message=r".*unauthenticated requests.*")
    # Import HF first (it configures its own logger on import), THEN override the
    # level — otherwise the import resets what we just set.
    try:  # the "Loading weights" bars are huggingface_hub-managed
        from huggingface_hub.utils import disable_progress_bars

        disable_progress_bars()
    except Exception:  # noqa: BLE001 - absent in some installs; harmless
        pass
    for name in ("huggingface_hub", "transformers", "sentence_transformers"):
        logging.getLogger(name).setLevel(logging.ERROR)

    # docling module loggers (the OCR "empty result" warning + INFO chatter).
    logging.getLogger("docling").setLevel(logging.WARNING)
    logging.getLogger("docling.models.stages.ocr.rapid_ocr_model").setLevel(logging.ERROR)

    _QUIETED = True
