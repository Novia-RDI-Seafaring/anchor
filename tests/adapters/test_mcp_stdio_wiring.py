"""MCP stdio assembly keeps document-search configuration usable."""
from __future__ import annotations

from anchor.adapters.mcp.stdio_main import _build_ingest_service
from anchor.extensions.anchor_pdfs.infra.llm.local_sentence_transformer_embedder import (
    LocalSentenceTransformerEmbedder,
)
from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder
from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig


def test_mcp_wires_configured_local_embedder_without_openai_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = AnchorConfig(data_dir=tmp_path, embed_model="local/test-model", _env_file=None)

    ingest = _build_ingest_service(config, MemoryEventBus(), MemoryDocStore())

    assert isinstance(ingest.embedder, LocalSentenceTransformerEmbedder)
    assert ingest.embed_model_id == "local/test-model"


def test_mcp_applies_openai_compatible_pipeline_configuration(tmp_path):
    config = AnchorConfig(
        data_dir=tmp_path,
        openai_api_key="test-key",
        openai_base_url="http://models.test/v1",
        polish_model="configured-polish",
        region_model="configured-regions",
        dpi=222,
        _env_file=None,
    )

    ingest = _build_ingest_service(config, MemoryEventBus(), MemoryDocStore())

    assert isinstance(ingest.polisher, OpenAIPageMdPolisher)
    assert ingest.polisher.base_url == "http://models.test/v1"
    assert isinstance(ingest.region_extractor, OpenAIRegionExtractor)
    assert ingest.region_extractor.base_url == "http://models.test/v1"
    assert isinstance(ingest.embedder, OpenAIEmbedder)
    assert ingest.embedder.base_url == "http://models.test/v1"
    assert ingest.embed_model_id == "text-embedding-3-large"
    assert ingest.default_polish_model == "configured-polish"
    assert ingest.default_region_model == "configured-regions"
    assert ingest.default_dpi == 222
