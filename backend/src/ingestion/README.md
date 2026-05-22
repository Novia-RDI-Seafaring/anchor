# Document Medallion Ingestion

This package contains Anchor's document medallion pipeline.

The pipeline turns an uploaded PDF into progressively richer artifacts:

```text
bronze/raw PDF
    -> silver/deterministic document structure
    -> gold/semantic regions and source-grounded crops
    -> query index and knowledge graph artifacts
```

Vector search can find relevant text, but Anchor also needs page images,
tables, diagrams, layout, and exact evidence regions. The medallion artifacts
store that information explicitly.

## Core Pipeline

- [pipeline.py](./pipeline.py) orchestrates `bronze -> silver -> gold`.
- [bronze.py](./bronze.py) handles raw PDF to Docling extraction.
- [silver.py](./silver.py) builds deterministic page markdown, page images, index, and metadata.
- [gold.py](./gold.py) extracts semantic regions and crops.
- [query_index.py](./query_index.py) builds and searches precomputed Q&A-style region queries.
- [knowledge_graph.py](./knowledge_graph.py) builds graph-style document knowledge artifacts.
- [embed.py](./embed.py) handles embedding helpers.
- [openai_clients.py](./openai_clients.py) wraps OpenAI/VLM calls for markdown polish and region extraction.
- [tags.py](./tags.py) defines known semantic region tags.
- [PIPELINE.md](./PIPELINE.md) contains the longer pipeline design notes.

## Layers

### Bronze

Bronze is the raw document layer.

Typical contents:

- original uploaded PDF

Main code:

- [bronze.py](./bronze.py)
- [pipeline.py](./pipeline.py)

### Silver

Silver is deterministic document structure.

Typical contents:

- `docling.json`
- `index.json`
- `pages.meta.json`
- `pages/N.png`
- `pages/N.raw.md`
- `pages/N.md`

Silver should be reproducible without LLM reasoning. It gives the app page-level text, page images, table/figure hints, and document navigation metadata.

Main code:

- [silver.py](./silver.py)
- [pipeline.py](./pipeline.py)

### Gold

Gold is semantic and visual evidence.

Typical contents:

- `pages/N.regions.json`
- cropped region PNG/SVG assets under `pages/N/`

Gold uses VLM/LLM extraction to identify meaningful page regions such as tables, diagrams, captions, text blocks, and spec blocks. These regions are what the UI can show, drag, and ground answers against.

Main code:

- [gold.py](./gold.py)
- [openai_clients.py](./openai_clients.py)
- [tags.py](./tags.py)

## Query And Graph Artifacts

The pipeline can also produce retrieval-friendly artifacts from the medallion data:

- [query_index.py](./query_index.py) creates precomputed natural-language queries and embeddings for gold regions.
- [knowledge_graph.py](./knowledge_graph.py) creates graph-style document knowledge artifacts.
- [embed.py](./embed.py) contains shared embedding helpers.

These artifacts let search results point back to a page, region, crop, and
document artifact instead of only a chunk of text.

## CLI And Agent Access

- [cli.py](./cli.py) adds a CLI for running and querying the pipeline.
- [mcp_server.py](./mcp_server.py) exposes pipeline access through MCP for external agents.
- [../../scripts/run_pipeline.py](../../scripts/run_pipeline.py) runs the pipeline from a script entrypoint.
- [../../scripts/reingest_all.py](../../scripts/reingest_all.py) reprocesses existing documents.

## Backend Integration

The ingestion package is wired into the backend in several places:

- [../knowledge_base/service.py](../knowledge_base/service.py) runs the pipeline on upload, tracks progress, and searches the query index.
- [../knowledge_base/vector_store.py](../knowledge_base/vector_store.py) stores the document registry in JSON-file-backed storage.
- [../knowledge_base/conversation_store.py](../knowledge_base/conversation_store.py) stores conversations in JSON-file-backed persistence.
- [../core/config.py](../core/config.py) provides `data_dir`; `data_dir/bronze` is the raw upload layer.
- [../api/routes_documents.py](../api/routes_documents.py) exposes API routes for pipeline status, pipeline detail, silver pages, gold regions, gold map, region assets, and query-index search.

## Agent Integration

The agent reads medallion artifacts through the existing document and product-data tools:

- [../agent/capabilities/context.py](../agent/capabilities/context.py) injects available document, pipeline, gold, and silver context into the agent.
- [../agent/tools/product_data.py](../agent/tools/product_data.py) loads gold and silver artifacts from the configured data directory.
- [../agent/tools/document.py](../agent/tools/document.py) reads pipeline data, page regions, silver pages, and gold maps.

## Design Rule

Keep the artifact boundary clear:

- Bronze stores the original source.
- Silver stores deterministic structure.
- Gold stores semantic evidence regions.
- Query and graph artifacts should point back to gold/silver provenance.

If retrieval is wrong, first check the artifact or ingestion layer before adding
downstream agent heuristics.
