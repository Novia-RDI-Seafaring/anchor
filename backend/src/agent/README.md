# Agent

The agent is a [PydanticAI](https://docs.pydantic.ai) agent that answers technical questions by searching a vector knowledge base and building a live knowledge graph on the canvas. It is streamed to the frontend via CopilotKit's coagent protocol.

## How it works

```
User question
    │
    ▼
RouterCapability.prepare_tools()   ← filters which tools are available this turn
    │
    ▼
RouterCapability.get_instructions()  ← injects per-query routing instruction
    │
    ▼
Agent runs (model calls tools, updates canvas state)
    │
    ▼
Canvas state streamed to frontend via CopilotKit
```

The agent's system prompt (`prompts.py`) is intentionally minimal. All domain logic lives in **capabilities** so it is easy to add, remove, or adjust behaviour without touching the core agent.

---

## Capabilities

A capability is a Python dataclass that implements `AbstractCapability`. Each capability can contribute:

- **A toolset** — the tools the model can call
- **Static instructions** — always included in the system context
- **Dynamic instructions** — a callable that inspects `RunContext` and returns instructions (or `None`) based on the live state

All capabilities are assembled in `capabilities/__init__.py` and passed directly to `Agent(capabilities=[...])`.

### CanvasCapability (`capabilities/canvas.py`)

Low-level canvas manipulation. Tools: `check_canvas`, `add_concept`, `add_topic`, `add_fact`, `add_spec_node`, `add_relation`, `update_node`, `delete_node`.

Instructions explain the **canvas hierarchy**:

```
concept → topic → fact / spec
```

- `concept` = the subject being studied (e.g. "Alfa Laval LKH-5")
- `topic` = an aspect of that subject (e.g. "Operating Limits", "Motor")
- `fact` / `spec` = a finding under that aspect, evidence-linked to a document

### KnowledgeCapability (`capabilities/knowledge.py`)

High-level RAG and search tools. Tools: `resolve_technical_query`, `compare_documents`, `search_knowledge_base`, `list_documents`, `get_active_document_context`.

`resolve_technical_query` is the primary tool — it runs a vector search, populates the canvas with a concept→topic→fact/spec tree, and returns a grounded summary. The model should call it multiple times (with the same `concept_id`) for multi-aspect queries.

Instructions cover intent routing: when to use high-level tools vs raw search, how to group findings under one concept, and the mandatory sequence for **comprehensive queries** ("tell me everything about X"):

1. `check_canvas()` — find existing concept node IDs to reuse
2. `get_document_tree()` — identify chapters and pages with tables/figures
3. `get_document_full_text()` — load full text + page images (cosine search misses table rows)
4. `resolve_technical_query()` × N aspects — same `concept_id` each time
5. `add_page_image_to_canvas()` — for every chart/table/diagram page

### DocumentVisionCapability (`capabilities/document_vision.py`)

Full-document and PDF image tools. Tools: `get_document_tree`, `get_document_full_text`, `analyze_pdf_page`, `add_page_image_to_canvas`, `analyze_image_content`.

Static instructions explain when to use each tool (e.g. read the tree before loading the full document, use `include_pages` to get visual renders of table/chart pages alongside text).

A **dynamic instruction** activates in full-context mode: if the deployment has a large-context model, the agent is told to load full documents instead of relying on cosine search.

### FmuCapability (`capabilities/fmu.py`)

Tools for working with FMU simulation models on the canvas. Separate from the knowledge tools so it can be routed independently.

### RouterCapability (`capabilities/router.py`)

No tools. Two responsibilities:

**1. Tool filtering (`prepare_tools`)**

Called before every model step. Inspects the prompt text via regex and returns a filtered tool list:

| Query pattern | Tools available |
|---|---|
| Social / meta ("hello", "what can you do") | `list_documents` only |
| Document listing ("what docs are loaded") | `list_documents` only |
| Explicit raw search ("search for X", "show me chunks") | search + list tools |
| Explicit canvas edit ("add this to canvas", "restructure") | all tools |
| Everything else | high-level technical tools (resolve, compare, vision, canvas) |

**2. Per-query dynamic instruction (`get_instructions`)**

Returns a focused instruction string that tells the model exactly how to handle the current query type:

- Raw retrieval → call `search_knowledge_base`, don't change canvas
- Canvas edit → prefer `resolve_technical_query`, use low-level tools only for restructuring
- Comparison → call `compare_documents` before answering
- Comprehensive → mandatory 5-step autonomous sequence, never ask "shall I continue?"
- Default technical → call `check_canvas` first, then `resolve_technical_query`, call multiple times for multi-aspect queries

---

## State and deps

**`state.py` — `Canvas`** is the coagent shared state. It is streamed live to the frontend.

```
Canvas
├── nodes: list[CanvasNode]   (concept / topic / fact / spec / image / fmu / plot)
├── relations: list[Relation] (edges between nodes, including evidence links to __doc_{id})
├── active_document_id        (document the user has focused)
└── workspace_doc_ids         (documents added to the current workspace)
```

**`deps.py` — `AgentDeps`** is passed to every tool call and contains the live `Canvas` state and a handle to the `RagEngine`.

---

## Adding a new capability

1. Create `capabilities/my_feature.py` — subclass `AbstractCapability`, define toolset + instructions.
2. Declare tool name sets (`HIGH_LEVEL_TOOLS`, etc.) so `RouterCapability` can filter them.
3. Register in `capabilities/__init__.py`: add to `_registry` and append to `CAPABILITIES`.
