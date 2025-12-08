# System Flow Diagrams

## 1. Simple Flow (High-Level Overview)

```mermaid
flowchart TB
    subgraph FRONTEND["Frontend (Next.js)"]
        UI[User Interface]
        CHAT[Chat Interface]
        MAIN[Main Content Area]
    end
    
    subgraph BACKEND["Backend (FastAPI :8001)"]
        API[API Routes]
        AGENT[PydanticAI Agent]
        DOC_SVC[Document Service]
    end
    
    subgraph STORAGE["Storage"]
        PG[(PostgreSQL + pgvector)]
        FILES[File System]
    end
    
    subgraph EXTERNAL["External Services"]
        LLM[OpenAI/Azure<br/>LLM & Embeddings]
    end
    
    UI -->|User Query| CHAT
    CHAT -->|POST /api/copilotkit| API
    API -->|AG-UI Request| AGENT
    AGENT -->|query_knowledge_base| DOC_SVC
    DOC_SVC -->|Vector Search| PG
    AGENT -->|LLM Call| LLM
    DOC_SVC -->|Embed Query| LLM
    AGENT -->|Response| CHAT
    CHAT -->|Display| MAIN
    
    UI -->|Upload File| API
    API -->|Upload| DOC_SVC
    DOC_SVC -->|Save File| FILES
    DOC_SVC -->|Process| LLM
    DOC_SVC -->|Store Chunks| PG
    
    style FRONTEND fill:#e1f5ff
    style BACKEND fill:#fff4e1
    style STORAGE fill:#e8f5e9
    style EXTERNAL fill:#fce4ec
```

## 2. Detailed Flow (Complete System Architecture)

```mermaid
flowchart TB
    subgraph FRONTEND["Frontend Layer (Next.js + React)"]
        direction TB
        PAGE[page.tsx<br/>Main App]
        COPILOT[CopilotKit Provider]
        CHAT_IFACE[ChatInterface.tsx]
        MAIN_CONTENT[MainContent.tsx]
        COMP_RENDERER[ComponentRenderer.tsx]
        SIDEBAR[Sidebar.tsx]
        API_ROUTE[api/copilotkit/route.ts]
    end
    
    subgraph BACKEND_API["Backend API Layer (FastAPI)"]
        direction TB
        MAIN_PY[main.py<br/>FastAPI App]
        AGENT_ENDPOINT[agent endpoint<br/>AG-UI Endpoint]
        DOC_API[api/documents<br/>Document APIs]
        SEARCH_API[api/search<br/>Search API]
        PAGE_API[api/documents/pages<br/>Page Images API]
        CHUNK_PAGE_API[api/chunks/pages<br/>Chunk-based Page Images API]
    end
    
    subgraph AGENT_LAYER["Agent Layer (PydanticAI)"]
        direction TB
        AGENT_PY[agent.py<br/>PydanticAI Agent]
        SYS_PROMPT[System Prompt]
        RAG_TOOLS[rag_tools.py]
        QUERY_TOOL[query_knowledge_base]
        RENDER_TOOL[render_ui_component]
        CHECK_TOOL[check_db_status]
        CONV_TOOL[add_to_conversation]
    end
    
    subgraph SERVICE_LAYER["Service Layer"]
        direction TB
        DOC_SVC[document_service.py<br/>DocumentService]
        VEC_STORE[vector_store.py<br/>VectorStore]
        EMBED_SVC[embeddings.py<br/>EmbeddingsService]
        PAGE_IMG_SVC[page_image_service.py<br/>PageImageService]
    end
    
    subgraph PROCESSING["Document Processing"]
        direction TB
        DOCLING[docling_converter.py<br/>DoclingConverter]
        FORMATTER[formatters.py<br/>MarkdownFormatter]
        HYBRID_CHUNKER[HybridChunker]
    end
    
    subgraph DATABASE["Database Layer"]
        direction TB
        PG[(PostgreSQL + pgvector)]
        DOCS_TBL[documents table]
        CHUNKS_TBL[chunks table<br/>with vector embeddings<br/>+ metadata page_numbers]
        PAGE_IMGS_TBL[page_images table]
        HNSW_IDX[HNSW Index<br/>for similarity search]
    end
    
    subgraph EXTERNAL_SERVICES["External Services"]
        direction TB
        OPENAI[OpenAI/Azure OpenAI]
        EMBED_API[Embeddings API<br/>text-embedding-ada-002]
        LLM_API[LLM API<br/>gpt-4o-mini/gpt-4o]
    end
    
    subgraph FILE_SYSTEM["File System"]
        UPLOADS[uploads/ directory]
    end
    
    %% Frontend Flow
    PAGE --> COPILOT
    COPILOT --> CHAT_IFACE
    COPILOT --> MAIN_CONTENT
    MAIN_CONTENT --> COMP_RENDERER
    CHAT_IFACE -->|User Message| API_ROUTE
    API_ROUTE -->|HTTP Request| AGENT_ENDPOINT
    
    %% Backend API Flow
    AGENT_ENDPOINT --> AGENT_PY
    DOC_API --> DOC_SVC
    SEARCH_API --> DOC_SVC
    PAGE_API --> VEC_STORE
    CHUNK_PAGE_API --> VEC_STORE
    
    %% Agent Processing Flow
    AGENT_PY --> SYS_PROMPT
    AGENT_PY --> RAG_TOOLS
    RAG_TOOLS --> QUERY_TOOL
    RAG_TOOLS --> RENDER_TOOL
    RAG_TOOLS --> CHECK_TOOL
    RAG_TOOLS --> CONV_TOOL
    QUERY_TOOL --> DOC_SVC
    RENDER_TOOL -->|State Update| AGENT_PY
    AGENT_PY -->|LLM Request| LLM_API
    
    %% Document Ingestion Flow
    DOC_SVC -->|Upload File| UPLOADS
    DOC_SVC -->|Process Document| DOCLING
    DOCLING -->|Convert PDF/DOCX| FORMATTER
    FORMATTER -->|Create Chunks| HYBRID_CHUNKER
    HYBRID_CHUNKER -->|Chunked Content| DOC_SVC
    DOC_SVC -->|Generate Embeddings| EMBED_SVC
    EMBED_SVC -->|API Call| EMBED_API
    DOC_SVC -->|Store Chunks| VEC_STORE
    DOC_SVC -->|Generate Page Images| PAGE_IMG_SVC
    PAGE_IMG_SVC -->|Store Images| VEC_STORE
    
    %% Search Flow
    DOC_SVC -->|Embed Query| EMBED_SVC
    DOC_SVC -->|Vector Search| VEC_STORE
    VEC_STORE -->|SQL Query| PG
    
    %% Page Image Query Flow (Chunk-based)
    CHUNK_PAGE_API -->|Get chunk by ID| CHUNKS_TBL
    CHUNK_PAGE_API -->|Extract page_numbers from metadata| CHUNKS_TBL
    CHUNK_PAGE_API -->|Query page images| PAGE_IMGS_TBL
    
    %% Database Operations
    VEC_STORE -->|INSERT/UPDATE| DOCS_TBL
    VEC_STORE -->|INSERT| CHUNKS_TBL
    VEC_STORE -->|INSERT| PAGE_IMGS_TBL
    CHUNKS_TBL --> HNSW_IDX
    VEC_STORE -->|SELECT with JOIN| DOCS_TBL
    VEC_STORE -->|SELECT with JOIN| CHUNKS_TBL
    VEC_STORE -->|SELECT by chunk_id| CHUNKS_TBL
    VEC_STORE -->|SELECT by document_id + page_numbers| PAGE_IMGS_TBL
    
    %% Response Flow
    AGENT_PY -->|Response + State| API_ROUTE
    API_ROUTE -->|Stream Response| CHAT_IFACE
    CHAT_IFACE -->|Display Message| MAIN_CONTENT
    MAIN_CONTENT -->|Render Components| COMP_RENDERER
    
    style FRONTEND fill:#e1f5ff
    style BACKEND_API fill:#fff4e1
    style AGENT_LAYER fill:#f3e5f5
    style SERVICE_LAYER fill:#e8f5e9
    style PROCESSING fill:#fff9c4
    style DATABASE fill:#fce4ec
    style EXTERNAL_SERVICES fill:#e0f2f1
    style FILE_SYSTEM fill:#f5f5f5
```

## Key Workflows

### Document Upload & Processing Flow
1. User uploads file → `POST /api/documents/upload`
2. `DocumentService.upload_file()` saves to `uploads/`
3. Generate `document_id` (MD5 hash)
4. Register in `documents` table
5. `process_document()`:
   - `DoclingConverter` converts PDF/DOCX → Markdown
   - `MarkdownFormatter` + `HybridChunker` creates chunks
   - Chunks include `page_numbers` in metadata (from document provenance)
   - `EmbeddingsService` generates embeddings via OpenAI
   - `VectorStore.add_chunks()` stores in `chunks` table (with metadata containing `page_numbers`)
   - `PageImageService` generates PDF page images (if PDF)
   - `VectorStore.add_page_images()` stores in `page_images` table
6. Update document status to `'processed'`

### Chat Query & RAG Flow
1. User sends message → `ChatInterface`
2. CopilotKit → `POST /api/copilotkit` → `HttpAgent` → `/agent`
3. `PydanticAI Agent` receives query
4. Agent calls `query_knowledge_base(query, top_k)` tool
5. Tool → `DocumentService.search()`:
   - Embed query via `EmbeddingsService`
   - `VectorStore.search()` performs cosine similarity search
   - PostgreSQL query with HNSW index
   - Returns top-k chunks with similarity scores, `document_id`, and `metadata` (including `page_numbers`)
6. Agent processes results and calls `render_ui_component()` if needed
7. Agent generates response using LLM with RAG context
8. Response streamed back through layers
9. Frontend displays message + UI components

### Page Image Query Flow (Chunk-based)
1. Frontend receives chunk data from RAG query (includes `chunk_id` or chunk metadata)
2. To fetch page images for a specific chunk:
   - Option A: `GET /api/chunks/{chunk_id}/pages/images`
     - `VectorStore.get_page_images_by_chunk_id(chunk_id)`:
       - Queries `chunks` table to get `document_id` and `metadata->page_numbers`
       - Queries `page_images` table using `document_id` and `page_numbers`
       - Returns page images for those specific pages
   - Option B: `POST /api/documents/{document_id}/pages/images` (with `page_numbers` from chunk metadata)
     - `VectorStore.get_page_images_for_pages(document_id, page_numbers)`
     - Direct query using known `document_id` and `page_numbers`
3. Page images returned as Base64-encoded PNG data
4. Frontend displays page previews in `PagePreviewDisplay` component

### UI Component Rendering Flow
1. Agent calls `render_ui_component(component_type, data)`
2. Updates `RAGState.active_ui_components`
3. State snapshot sent to frontend
4. `MainContent` receives state via `useCoAgent()`
5. `ComponentRenderer` renders appropriate component:
   - `ListDisplay` for lists
   - `TableDisplay` for tables
   - `ImageDisplay` for images
   - `PagePreviewDisplay` for PDF page previews
6. For `PagePreviewDisplay`:
   - If `chunk_id` is available: fetches from `/api/chunks/{chunk_id}/pages/images`
   - Otherwise: fetches from `/api/documents/{document_id}/pages/images` with `page_numbers` from chunk metadata
7. Component displays page images with navigation controls

## Page Image Query Methods

### Available Query Methods

1. **By Document ID and Page Numbers** (`get_page_images_for_pages`)
   - Endpoint: `POST /api/documents/{document_id}/pages/images`
   - Method: `VectorStore.get_page_images_for_pages(document_id, page_numbers)`
   - Use case: When you know the document and specific page numbers

2. **By Chunk ID** (`get_page_images_by_chunk_id`) ⭐ **NEW**
   - Endpoint: `GET /api/chunks/{chunk_id}/pages/images`
   - Method: `VectorStore.get_page_images_by_chunk_id(chunk_id)`
   - Use case: When you have a chunk ID from RAG search results
   - Process:
     1. Query `chunks` table to get `document_id` and `metadata->page_numbers`
     2. Query `page_images` table using retrieved `document_id` and `page_numbers`
     3. Return matching page images

3. **Single Page by Document ID** (`get_page_image`)
   - Endpoint: `GET /api/documents/{document_id}/pages/{page_number}/image`
   - Method: `VectorStore.get_page_image(document_id, page_number)`
   - Use case: Fetching a single specific page

## Data Flow Summary

**Ingestion**: File/URL → Docling → Chunking (with page_numbers in metadata) → Embedding → PostgreSQL  
**Query**: User Question → Agent → Tool → Vector Search → Context (chunks with page_numbers) → LLM → Response  
**Page Images**: Chunk ID → Query chunks table → Extract page_numbers → Query page_images table → Return images  
**Storage**: PostgreSQL with pgvector extension for similarity search  
**UI**: Agent State → Frontend → Component Rendering → Page Image Query (by chunk_id) → User Display
