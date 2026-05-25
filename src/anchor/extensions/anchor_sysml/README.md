# anchor_sysml

OIP-compliant SysML v2 producer for the Anchor canvas. Phase 1 lands the
ingestion side: parse SysML v2 textual notation, project the result to
canvas nodes/edges, and emit a stub for round-trip export.

## Phase 1 — what works today

- **Lexer + parser** for the documented Phase-1 subset:
  `package`, `part def`, `part`, `attribute (def)`, `value`, `port (def)`
  with `in`/`out`/`inout` direction, `item (def)`, `interface … connect …
  to`, `requirement (def)`, `subject`, `assert constraint { … }`, `satisfy
  … by …`, `import`, `doc /* … */`, plus the relationship operators `:`,
  `:>`, `:>>`, `::>`, `=`.
- **Canvas mapper** turns the IR into `sysml:block`, `sysml:requirement`,
  `sysml:package` nodes with the documented `data` shape, and edges
  carrying a `data.marker` of `inheritance | redefinition | subset |
  composition | interface-connection | satisfy | subject | association`.
- **Service** (`SysmlService.render`) parses + maps + dispatches via the
  canvas-primitive `WorkspaceService` so SysML imports ride the same SSE,
  persistence, and version stream as everything else on the canvas.
- **Layout** is a simple grid (4 columns, 280×200 cells, 80px gutter).

## What's deferred

- Action diagrams, state machines, transitions, flows, calc and metadata
  *bodies* are recognised but skipped — a non-fatal `Diagnostic` is added
  to the render result so the agent / canvas can surface it.
- Phase 2 will fold in:
  - The SysML v2 Pilot Implementation API (cross-file resolution).
  - Action / state / transition mapping to canvas action and state nodes.
  - **ISO 15926 RDL resolution** — `metadata { @iso15926-uri = "…"; }`
    payloads are preserved verbatim in `node.data.metadata` today and
    never interpreted, so the future RDL-aware consumer can light up
    automatically without touching parser output.
- `SysmlService.export` returns a stub header in Phase 1 so agents have a
  callable contract, but the real renderer (the `SysmlRenderer` port) is
  the seam for faithful round-trip in Phase 2.

## Where things live

- `core/schemas.py` — IR types + canvas spec types (parser/mapper output).
- `core/ports.py` — `SysmlParser`, `CanvasMapper`, `SysmlRenderer`.
- `core/services.py` — `SysmlService` (orchestrates the three pipelines).
- `core/events.py` — `SysmlRendered`, `SysmlExported`, `SysmlRenderFailed`.
- `infra/lexer.py` — token scanner.
- `infra/parser.py` — recursive-descent grammar.
- `infra/canvas_mapper.py` — IR → canvas batch projection.
- `adapters/http/sysml_routes.py` — `POST /api/sysml/render`, `GET /api/sysml/export`.
- `mcp_handlers.py` — `sysml.render`, `sysml.export`.

## Test fixtures

`tests/extensions/anchor_sysml/fixtures/`:

- `drone_base_architecture.sysml` (vendored, BSD-3) — requirements + satisfy.
- `mining_frigate.sysml` (vendored, BSD-3) — ports + interfaces + ref parts.
- `lkh_pump.sysml` — authored example for the LKH centrifugal-pump demo.
