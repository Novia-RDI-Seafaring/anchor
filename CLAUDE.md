# Anchor KB — Knowledge-Grounded Engineering Canvas

## Python

the backend is python
we use uv.

## What this app does

A full-stack tool for engineers to work with technical documents (PDF datasheets, product leaflets) alongside simulation models (FMUs). An AI agent reads documents, extracts structured data, and helps connect document-sourced parameters to simulation inputs.

The core workflow:
1. Upload technical documents (PDF) into the knowledge base
2. Add them to a visual canvas
3. Ask the AI agent to extract specs, operating data, parameter tables
4. Get grounded, source-referenced data tables on the canvas
5. Wire extracted values into FMU simulation parameters
6. Run simulations directly from the canvas

## Architecture

### Frontend (`/src`)
- **Next.js 15** (App Router), React 19, Tailwind CSS
- **CopilotKit** (`@copilotkit/react-core` + `@copilotkit/react-ui`, v1.51) for chat/agent UI
- **React Flow** (`@xyflow/react`) for the canvas graph
- API route at `/api/copilotkit` proxies to backend via `HttpAgent` from `@ag-ui/client`

### Backend (`/backend`)
- **FastAPI** + asyncpg + pgvector
- **PydanticAI** agent with AG-UI protocol, endpoint at `/agent`
- Runs at `localhost:8001`

### Database
- PostgreSQL, schema `anchor`
- Tables: `documents`, `conversations` (JSONB for `messages` and `canvas_state`)

## Canvas node types

The canvas uses React Flow with custom node types:

| Node type | Purpose | Key file |
|-----------|---------|----------|
| `document` | PDF/document card with cover image, handles for connecting | `KnowledgeNodes.tsx` |
| `spec` | Parameter/spec table with row-level source refs | `KnowledgeNodes.tsx` |
| `fmu` | FMU simulation node with inputs/outputs/parameters | `KnowledgeNodes.tsx` |
| `model` | Named model bridge (e.g. "LKH-5 Pump") connecting docs to FMUs | `KnowledgeNodes.tsx` |
| `concept` | Box shape — general purpose grouping node | `KnowledgeNodes.tsx` |
| `entity` | Circle shape — product/system root | `KnowledgeNodes.tsx` |
| `fact` | Text/note card with markdown | `KnowledgeNodes.tsx` |
| `area` | Dashed container region, other nodes can be parented inside | `KnowledgeNodes.tsx` |
| `funnel` | Diamond shape | `KnowledgeNodes.tsx` |
| `plot` | Simulation result chart | `KnowledgeNodes.tsx` |
| `image` | PDF page screenshot | `KnowledgeNodes.tsx` |

### Model node (new, 2026-04-02)

The **model node** is a semantic bridge between documents and FMU parameters. It represents a named engineering model (e.g. "Pump", "Heat Exchanger"). The intended flow:

- **Document → Model node**: "this is the source document for this model"
- **Model node → FMU**: "find the parameters this FMU needs from the connected documents"
- **Model node → Canvas**: "extract specific data sections (description, param tables, curves)"

The model node has an inline-editable label (double-click to rename). Toolbar shortcut: `6`.

### Edge types

- `floating` — loose graph edges (automatic routing)
- `anchored` — explicit handle-to-handle connections (row-level wiring, evidence edges)

## Canvas key files

| File | Role |
|------|------|
| `src/components/canvas/CanvasGraph.tsx` | Main canvas component — node/edge building, toolbar, drag-drop, layout |
| `src/components/canvas/KnowledgeNodes.tsx` | All node renderers (document, spec, fmu, model, etc.) |
| `src/components/canvas/canvas-model.ts` | TypeScript types for canvas items, legacy node adaptation |
| `src/components/canvas/FloatingEdge.tsx` | Floating edge renderer |
| `src/components/canvas/AnchoredEdge.tsx` | Handle-anchored edge renderer |
| `src/components/canvas/PDFModal.tsx` | PDF viewer modal |
| `src/components/layout/MainContent.tsx` | Canvas state management, event handlers (add/delete/update nodes) |

## Backend agent structure

### Capabilities (`/backend/src/agent/capabilities/`)
- `context.py` — injects canvas state + document list into agent context, provides `read_document_page`
- `canvas.py` — canvas node/relation CRUD tools
- `product_data.py` — gold-layer product data lookup tool
- `knowledge.py` — knowledge graph behavior instructions (currently disabled)
- `router.py` — intent routing (currently disabled)
- `fmu.py` — FMU/simulation behavior (currently disabled)
- `document_vision.py` — vision-based document reading (currently disabled)
- `engineering_knowledge/` — domain reference material (pump curves, etc.)

### Tools (`/backend/src/agent/tools/`)
- `knowledge.py` — RAG search, spec/fact table creation
- `document.py` — page reading, page images, bbox extraction
- `canvas.py` — canvas node manipulation, bbox backfill
- `fmu.py` — FMU upload, simulation execution
- `vision.py` — vision tools
- `product_data.py` — gold-layer lookup: `get_product_data(document_id)` returns pre-extracted structured JSON with bboxes

## Document Ingestion Pipeline (Bronze / Silver / Gold)

Three-layer medallion architecture for transforming PDFs into structured, queryable product knowledge.

| Layer | Path | Contents |
|-------|------|----------|
| **Bronze** | `backend/data/uploads/` | Raw PDF files + `files_index.json` |
| **Silver** | `backend/data/silver/<slug>/` | Docling extraction output — items with type, text, page, bbox |
| **Gold** | `backend/data/gold/` | Structured product knowledge JSON, one per document |

**Full spec:** `backend/data/INGESTION_PIPELINE_SPEC.md`

### Gold JSON structure
- Mirrors actual document section hierarchy (not reorganized)
- Every section/table/item has `page` and `bbox` (BOTTOMLEFT coordinates, from Docling)
- Table types: `property_table` (same for all models), `model_dependent_table` (values vary by model), `model_table` (one column per model), `motor_table` (one column per IEC frame)
- Reference example: `backend/data/gold/alfa-laval-lkh-centrifugal-pump.json` (Alfa Laval LKH pump, 4 pages, 13 models)

### Agent integration
- **Capability:** `backend/src/agent/capabilities/product_data.py` → `ProductDataCapability`
- **Tool:** `get_product_data(filename)` — returns full gold JSON in one call
- **Lookup:** matches filename against gold JSON `document.filename` field directly (no dependency on files_index.json or document IDs)
- Agent tries gold data first, falls back to `read_document_page()` if no gold exists
- Currently active capabilities: `ContextCapability`, `CanvasCapability`, `ProductDataCapability`

### Pipeline roadmap
1. **Phase 1 (current):** Gold JSON hand-crafted, silver saved as reference
2. **Phase 2:** LLM-assisted extraction (silver → gold draft) + verification agent
3. **Phase 3:** Agent tagging tools (semantic tags, model scoping, cross-doc links, verification status)
4. **Phase 4:** Fully automated on-upload pipeline

## Key design rules

- **FMU nodes are separate from the knowledge graph.** The agent should not auto-connect knowledge nodes to FMUs. Manual wiring from spec table rows to FMU parameters is allowed.
- **Row-level provenance.** Each row in a spec table carries its own `ParameterSource` (doc_id, filename, page, bbox). Source edges are visible on the canvas.
- **One table per extraction.** When extracting operating/spec data, produce one grounded table — don't split into many small nodes.

## CopilotKit notes

- Use `useCopilotChatInternal` (not `useCopilotChat`) for `setMessages`/`messages` access
- Do NOT use `@copilotkitnext/react` — it's deprecated
- Custom `Input` component receives `onSend` and `inProgress` as props

## FMU library

External FMU files are in `/Users/toffe/dev/ai/novia/fmu-library` (branch `refactor/engine-cooling-fmus`). Engine cooling system components:
- `pump_FMI2.fmu` — inputs: temp_in [degC], mass_in [kg/s], pump_value [kg/s]; outputs: temp_out, mass_out
- `control_valve_FMI2.fmu`, `engine_heat_load_FMI2.fmu`, `heat_exchanger_FMI2.fmu`, `mixer_FMI2.fmu`
- System-level: `LOC_31032026_FMI2.fmu`, `LOC_System_31032026_FMI2.fmu`, `LOC_Control_31032026_FMI2.fmu`

## Development

```bash
# Frontend
npm run dev          # localhost:3000

# Backend
cd backend
source .venv/bin/activate
uvicorn src.main:app --reload --port 8001
```

## Git

- Do not add "Co-Authored-By" trailers to commits
