# Backend workflow diagram:

## Mermaid Diagram

```mermaid
flowchart TB
    subgraph API["FastAPI Backend (Port 8001)"]
        AGENT["/agent<br/>(AG-UI)"]
        DOCS["/api/*<br/>(Document APIs)"]
    end

    subgraph AGENT_FLOW["Agent Workflow"]
        USER[User Query] --> AGENT
        AGENT --> AGENT_PY[agent.py<br/>PydanticAI Agent]
        AGENT_PY --> TOOLS{Agent Tools}
        TOOLS -->|query_knowledge_base| DOC_SVC[document_service.search]
        TOOLS -->|check_db_status| STATUS[DB Status Check]
        TOOLS -->|add_to_conversation| CONV[Update History]
        DOC_SVC --> VEC_SEARCH[vector_store.search]
        VEC_SEARCH --> RESPONSE[Response with RAG Context]
    end

    subgraph INGEST["Document Ingestion"]
        UPLOAD[Upload/URL] --> DOC_SVC2[DocumentService]
        DOC_SVC2 --> SAVE[Save to uploads/]
        SAVE --> GEN_ID[Generate Document ID]
        GEN_ID --> REG[Register in DB]
        REG --> PROCESS[process_document]
        PROCESS --> DOCLING[DoclingConverter<br/>PDF/DOCX → Markdown]
        DOCLING --> CHUNK[MarkdownFormatter<br/>Split into chunks]
        CHUNK --> EMBED[embeddings_service<br/>Generate embeddings]
        EMBED --> STORE[vector_store.add_chunks<br/>Store in PostgreSQL]
        STORE --> DONE[Status: processed]
    end

    subgraph SEARCH_FLOW["Search Workflow"]
        QUERY[Search Query] --> DOC_SEARCH[document_service.search]
        DOC_SEARCH --> QUERY_EMBED[Embed query]
        QUERY_EMBED --> VEC_QUERY[vector_store.search]
        VEC_QUERY --> PG_QUERY[PostgreSQL<br/>Cosine Similarity]
        PG_QUERY --> RESULTS[Return chunks + scores]
    end

    subgraph EXTERNAL["External Services"]
        PG[(PostgreSQL + pgvector<br/>documents & chunks tables)]
        OPENAI[OpenAI/Azure OpenAI<br/>Embeddings & LLM]
    end

    VEC_SEARCH --> PG
    STORE --> PG
    VEC_QUERY --> PG
    EMBED --> OPENAI
    QUERY_EMBED --> OPENAI
    AGENT_PY --> OPENAI

    style API fill:#e1f5ff
    style AGENT_FLOW fill:#fff4e1
    style INGEST fill:#e8f5e9
    style SEARCH_FLOW fill:#f3e5f5
    style EXTERNAL fill:#fce4ec
```

**Key Components:**

1. **FastAPI App** (`main.py`): Entry point, mounts AG-UI agent and exposes REST APIs
2. **Agent** (`agent.py`): PydanticAI agent with tools for RAG queries
3. **DocumentService** (`document_service.py`): Orchestrates document processing pipeline
4. **VectorStore** (`vector_store.py`): Manages PostgreSQL + pgvector for embeddings
5. **EmbeddingsService** (`embeddings.py`): Generates embeddings via OpenAI/Azure
6. **DoclingConverter** (`docling_processing/`): Converts PDFs/DOCX to markdown

**Data Flow Summary:**
- **Ingestion**: File/URL → Docling → Chunking → Embedding → PostgreSQL
- **Query**: User question → Agent → Tool call → Vector search → Context → LLM → Response
- **Storage**: PostgreSQL with pgvector extension for similarity search

The agent uses the `query_knowledge_base` tool during conversations to retrieve relevant context from the vector store before generating responses.
