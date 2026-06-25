"""Model provisioning + offline enforcement for local-only ingests.

Anchor's local stages load two model families from the HuggingFace hub on first
use: the sentence-transformer embedder (``BAAI/bge-small-en-v1.5``) and
docling's layout / OCR models. On a locked-down host that first-run download is
unexpected outbound traffic. This module is the one place that:

- names the *required model set* for a local-only ingest, so
  ``anchor models prefetch`` can warm the cache ahead of time, and
- enforces the HuggingFace *offline* env (``HF_HUB_OFFLINE`` /
  ``TRANSFORMERS_OFFLINE``) so a later run loads only cached weights and never
  reaches ``huggingface.co``.

Offline mode composes with the existing data-zone model (``anchor.infra.
environment``): local-only is a property of the resolved config, not a new
mechanism. ``enforce_offline`` is ``setdefault``-based so an operator who has
already exported the offline vars (or who wants them *off* for a one-time
prefetch) is always respected.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

#: HuggingFace offline switches. Both are read at *import* time by their
#: respective libraries, so they must be set before the embedder / docling are
#: first imported (the CLI sets them at startup when local-only is active).
HF_OFFLINE_VARS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")

#: The embedding model is fixed to bge-small: the in-browser query embedder is
#: pinned to it, so a different local model would break browser search (vector
#: space mismatch). See ``anchor.infra.providers.LOCAL_EMBED_OPTIONS``.
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass(frozen=True)
class ModelSpec:
    """One model required for a local ingest, with how to fetch it."""

    #: HuggingFace repo id (embedder) or a docling family label.
    repo_id: str
    #: ``embed`` (sentence-transformers) or ``docling`` (layout + OCR bundle).
    kind: str
    #: Human one-liner for the prefetch report.
    note: str


def required_models(embed_model: str = DEFAULT_EMBED_MODEL) -> tuple[ModelSpec, ...]:
    """The model set a local-only ingest needs cached before going offline.

    A *remote* embedder (``text-embedding-*``) needs nothing local — it never
    loads weights — so it is omitted; only the on-host bge model and the docling
    layout/OCR bundle are returned.
    """
    specs: list[ModelSpec] = []
    if not embed_model.startswith("text-embedding-"):
        specs.append(
            ModelSpec(
                repo_id=embed_model,
                kind="embed",
                note="sentence-transformer embedder (local search vectors)",
            )
        )
    specs.append(
        ModelSpec(
            repo_id="docling",
            kind="docling",
            note="docling layout + OCR models (bronze extraction)",
        )
    )
    return tuple(specs)


def offline_active() -> bool:
    """True when either HuggingFace offline switch is set truthy in the env."""
    return any(_truthy(os.environ.get(var)) for var in HF_OFFLINE_VARS)


def enforce_offline() -> list[str]:
    """Pin HuggingFace loading offline for a local-only run. Idempotent.

    Sets ``HF_HUB_OFFLINE`` / ``TRANSFORMERS_OFFLINE`` with ``setdefault`` so an
    operator's explicit value (including a deliberate ``0`` for a prefetch) is
    never overridden. Returns the variables this call newly set, for an
    auditable echo.
    """
    newly_set: list[str] = []
    for var in HF_OFFLINE_VARS:
        if var not in os.environ:
            os.environ[var] = "1"
            newly_set.append(var)
    return newly_set


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def prefetch_models(embed_model: str = DEFAULT_EMBED_MODEL) -> list[dict[str, object]]:
    """Download the required model set so a later offline ingest works.

    Loads each model exactly as ingest would (sentence-transformers for the
    embedder, docling's converter for layout/OCR), which populates the
    HuggingFace cache. Must run with network access; an offline env would defeat
    the point, so this deliberately does NOT call :func:`enforce_offline`.

    Returns one result dict per model: ``{repo_id, kind, ok, detail}``. A
    failure is reported (``ok=False``) rather than raised, so a partial prefetch
    still tells the operator which models are missing.
    """
    results: list[dict[str, object]] = []
    for spec in required_models(embed_model):
        try:
            if spec.kind == "embed":
                _warm_embedder(spec.repo_id)
                detail = "cached"
            else:
                _warm_docling()
                detail = "cached"
            results.append(
                {"repo_id": spec.repo_id, "kind": spec.kind, "ok": True, "detail": detail}
            )
        except Exception as exc:  # noqa: BLE001 - report, don't abort the batch
            results.append(
                {"repo_id": spec.repo_id, "kind": spec.kind, "ok": False, "detail": str(exc)}
            )
    return results


def _warm_embedder(model_id: str) -> None:
    """Force the sentence-transformer weights into the cache."""
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(model_id)


def _warm_docling() -> None:
    """Force docling's layout + OCR models into the cache.

    docling downloads its models lazily on the first ``convert``; building the
    converter with the same options ingest uses (RapidOCR onnxruntime backend)
    pulls every weight a real ingest needs.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        RapidOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.ocr_options = RapidOcrOptions(backend="onnxruntime")
    DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
