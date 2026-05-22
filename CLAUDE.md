# Anchor KB - Contributor Engineering Notes

Anchor is a local-first engineering canvas for technical PDFs, structured
document evidence, and FMU simulation models. Keep this file aligned with the
live code. If a module exists but is not registered or wired, describe it as
dormant or in progress.

## Stack

### Frontend (`src/`)

- Next.js 15 App Router, React 19, Tailwind CSS.
- CopilotKit v1.51 (`@copilotkit/react-core`, `@copilotkit/react-ui`,
  `@copilotkit/runtime`) for chat UI and runtime integration.
- React Flow (`@xyflow/react`) for the canvas graph.
- The CopilotKit route is `src/app/api/copilotkit/route.ts`.
- The route forwards to the backend AG-UI endpoint with `HttpAgent` from
  `@ag-ui/client`.

### Backend (`backend/`)

- Python 3.12. Use `uv` for dependency management and execution.
- FastAPI app entry point: `backend/main.py`.
- PydanticAI agent exposed through AG-UI and mounted at `/agent`.
- Local backend default: `http://localhost:8001`.
- PostgreSQL/pgvector settings may exist for future vector storage, but they
  are not required for the current local runtime.
- The current document registry is JSON-file-backed in
  `backend/data/store/documents.json`.
- The current conversation store is JSON-file-backed under
  `backend/data/store/conversations/`.

## Local Workflow

```bash
npm install
cd backend
uv sync
copy .env.example .env
cd ..
npm run dev
```

Edit `backend/.env` with one LLM provider configuration before running the app.
No PostgreSQL setup is required for the default local workflow.

Write routes allow loopback requests by default. For a shared or public
deployment, set `ANCHOR_WRITE_API_KEY`, set
`ALLOW_UNSAFE_LOCAL_WRITES=false`, and put the backend behind HTTPS and an
application-level auth boundary.

## Product Workflow

1. Upload technical documents, usually PDF datasheets or product leaflets.
2. Add documents to the visual canvas.
3. Ask the agent to extract specs, operating data, parameter tables, or
   evidence-backed notes.
4. Show grounded tables and facts on the canvas with source references.
5. Wire extracted values manually into FMU inputs or parameters.
6. Run simulations from the canvas and inspect resulting plot nodes.

## Canvas

The canvas uses React Flow with custom node and edge renderers.

Key files:

| File | Role |
| --- | --- |
| `src/components/canvas/CanvasGraph.tsx` | Main graph component: node and edge construction, toolbar, drag/drop, layout, selection |
| `src/components/canvas/KnowledgeNodes.tsx` | Renderers for document, spec, FMU, model, image, plot, shapes, notes, and related nodes |
| `src/components/canvas/canvas-model.ts` | Frontend canvas item types and legacy node adaptation |
| `src/components/canvas/canvasGraphUtils.ts` | Node sizing, evidence edges, source coloring, graph helpers |
| `src/components/canvas/canvasGraphLayoutUtils.ts` | Layout and positioning helpers |
| `src/components/canvas/FloatingEdge.tsx` | Loose graph edge renderer |
| `src/components/canvas/AnchoredEdge.tsx` | Explicit handle-to-handle edge renderer |
| `src/components/canvas/PDFModal.tsx` | PDF viewer modal and highlights |
| `src/components/workspace-v2/WorkspaceV2App.tsx` | Active workspace shell: chat composer, activity drawer, medallion panel, canvas state, and agent wiring |
| `src/components/layout/mainContentUtils.ts` | Shared canvas normalization and document screenshot helpers |

Core semantic nodes:

| Node type | Purpose |
| --- | --- |
| `document` | PDF/document card with cover image and connection handles |
| `spec` | Parameter/spec table with row-level source references |
| `fmu` | FMU simulation node with inputs, outputs, and parameters |
| `model` | Named engineering model bridge between documents and FMUs |
| `fact` | Markdown note or extracted textual fact |
| `image` | PDF page screenshot or cropped document region |
| `plot` | Simulation result chart |

Canvas organization and legacy/support nodes include `concept`, `topic`,
`entity`, `category`, `source`, `area`, `funnel`, `square`, `circle_shape`,
`diamond_shape`, `note`, and `rich_text`.

## Agent Runtime

The live agent is intentionally smaller than the broader architecture present
under `backend/src/agent/`.

Registered capabilities are defined in
`backend/src/agent/capabilities/__init__.py`:

- `ContextCapability`
- `CanvasCapability`

Dormant or in-progress capabilities currently present in the tree:

- `ProductDataCapability`
- `KnowledgeCapability`
- `DocumentVisionCapability`
- `FmuCapability`
- `EngineeringKnowledgeCapability`
- `RouterCapability`

Do not describe dormant capabilities as active runtime behavior unless they are
added to `CAPABILITIES`.

## Document Ingestion

The ingestion pipeline uses a Bronze/Silver/Gold medallion structure.

| Layer | Path | Contents |
| --- | --- | --- |
| Bronze | `backend/data/bronze/` | Raw uploaded PDFs |
| Silver | `backend/data/silver/<slug>/` | `docling.json`, `index.json`, `pages.meta.json`, page markdown, page PNGs |
| Gold | `backend/data/gold/<slug>/` | Semantic page regions, crops, and evidence assets |

Gold regions are semantic visual atoms such as tables, charts, diagrams,
captions, text blocks, or spec blocks. Each region should carry page and bbox
provenance.

## Engineering Rules

- FMU nodes are separate from the knowledge graph. The agent should not
  automatically connect knowledge nodes to FMUs.
- Manual wiring from spec table rows to FMU inputs or parameters is allowed.
- Preserve row-level provenance. Each spec row should carry its own
  `ParameterSource` (`doc_id`, `filename`, `page`, `bbox`) whenever possible.
- Source/evidence edges should remain visible on the canvas.
- Prefer one grounded table per extraction instead of many small table nodes.
- When structured gold data exists, use it before page reading or RAG.
- When region gold exists, use it for source-grounded visual evidence.
- Keep agent docs aligned with the live `CAPABILITIES` registration.

## CopilotKit Notes

- Use `useCopilotChatInternal` when code needs `setMessages` or direct
  `messages` access.
- Do not use `@copilotkitnext/react`; it is deprecated.
- The custom chat input receives `onSend` and `inProgress` props.

## Git

- Do not add `Co-Authored-By` trailers to commits.
- The worktree may contain user changes. Do not revert unrelated changes.
