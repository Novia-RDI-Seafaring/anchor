# Agent

This branch currently runs a small [PydanticAI](https://docs.pydantic.ai) agent streamed to the frontend through CopilotKit coagent state.

## Live flow

```
User question
    │
    ▼
Agent preamble (`prompts.py`)
    │
    ▼
Live capabilities
  - ContextCapability
  - CanvasCapability
    │
    ▼
Tool calls update shared canvas state
    │
    ▼
Canvas state streamed to the frontend
```

The key point on `feat/skills` is that the runtime is smaller than the broader architecture present in the folder.

## Active capabilities

The current runtime only registers the capabilities listed in [capabilities/__init__.py](./capabilities/__init__.py):

- `ContextCapability`
- `CanvasCapability`

### ContextCapability

Responsibilities:

- inject current canvas state into agent context
- inject the available document list
- auto-load gold-layer product data for document nodes already on the canvas
- expose `read_document_page(...)`

This capability currently mixes context assembly and document-reading support.

### CanvasCapability

Responsibilities:

- expose low-level canvas mutation tools
- describe the parameter-table format expected by `add_spec_node(...)`

Current registered tools:

- `check_canvas`
- `add_concept`
- `add_topic`
- `add_fact`
- `add_spec_node`
- `update_node`
- `delete_node`
- `add_relation`

## Important branch note

This branch also contains additional capability modules such as:

- `knowledge.py`
- `document_vision.py`
- `router.py`
- `fmu.py`
- `product_data.py`

Those files are present, but they are not currently registered in the live `CAPABILITIES` list. Treat them as dormant or in-progress architecture until they are explicitly enabled.

## State and deps

`state.py` defines the shared `Canvas` state streamed to the frontend. It holds:

- nodes
- relations
- `active_document_id`
- `workspace_doc_ids`

`deps.py` defines `AgentDeps`, which gives tools access to the live canvas state and the `RagEngine`.

## Maintainability rule for this branch

When editing this agent, prefer:

- keeping the live capability set explicit
- keeping docs aligned with what is actually registered
- separating context assembly from domain logic where possible

Avoid describing dormant capabilities as if they are already part of the runtime.
