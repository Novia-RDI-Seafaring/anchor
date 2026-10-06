# Reusing the intent layer

`intent_layer` is an internal Python namespace shipped in the `anchor-kb`
wheel and source distribution. It imports without the `anchor` package and
does not create a server or load transport adapters at import time. There is
no separate published distribution or process.

The module owns durable request records, thread transitions, actor context,
count signals and reusable inbox transports. A host owns target validation and
encoding, revision lookup, operation validation, applying changes and undo.
Targets can be opaque finite JSON values such as `["email", "max_flow"]`.
The service never interprets their keys. Operations remain objects interpreted
by the host; they are not executable code.

## Modules and ownership

| Module | Responsibility |
| --- | --- |
| `intent_layer.models` | Intent and thread item records, legacy persistence format |
| `intent_layer.actor` | Canonical Actor and the shared ContextVar |
| `intent_layer.errors` | Stable rejection codes and application failure facts |
| `intent_layer.ports` | Store, host, application result and attribution context |
| `intent_layer.service` | Inbox and thread state transitions with an explicit host |
| `intent_layer.fs_store`, `memory_store` | Durable and in-memory intent stores |
| `intent_layer.signals` | Count-only signal port and in-process implementation |
| `intent_layer.adapters.http` | Mounted FastAPI router factory |
| `intent_layer.adapters.mcp` | Tool definitions and JSON dispatch |
| `intent_layer.adapters.cli` | Mountable Typer inbox factory |

Anchor retains its canvas commands, batch validation, inverse generation,
event envelope, event bus and project composition. `AnchorThreadHost` is its
host implementation. `AnchorPendingSignals` converts generic count signals to
the existing `IntentPending` event with `{count}` and the original timestamp.
The legacy `_project` sentinel is also a valid canvas slug. The bridge preserves
that literal scope when reading rather than guessing whether it meant no origin
or a real `_project` canvas.

Old Anchor model, error, Actor/context, ThreadHost and MemoryIntentStore imports
are aliases to the canonical objects. The Anchor IntentService constructor is
an intentional compatibility wrapper: `workspace=` still creates an Anchor host,
and an explicit `host=` wins. Anchor FsIntentStore is a compatibility wrapper
that preserves UnsafeUploadError for refused filenames. Anchor CLI help and MCP
schemas remain host-specific; their service and dispatch paths are shared.

## Compose a host and mount its inbox

Implement `ThreadHost` from `intent_layer.ports`. Its methods are
`ensure_available`, `validate_targets`, `encode_targets`, `decode_targets`,
`validate_ops`, `base_version`, `apply` and `revert`. `apply` returns an
`AppliedSuggestion` with undo operations, versions and host result metadata.
`ThreadContext` carries intent and item IDs, origin, decoded targets, the
suggestion author and the current approver. The host uses the item ID as the
causation reference. Revert attribution remains a host responsibility.

```python
from pathlib import Path

from fastapi import FastAPI
from intent_layer.adapters.http import create_router
from intent_layer.fs_store import FsIntentStore
from intent_layer.service import IntentService
from intent_layer.signals import MemoryPendingSignals

# form_host implements ThreadHost and owns the form's values and revision.
signals = MemoryPendingSignals()
service = IntentService(FsIntentStore(Path("form-data")), signals, host=form_host)
app = FastAPI()
app.include_router(create_router(lambda: service, lambda: signals,
                                 prefix="/form/inbox"))
```

The HTTP inbox supports list pending, list all, create, get and resolve, plus
add/update item, answer, apply, revert and decline. `/events` sends an initial
pending-count snapshot, then count nudges. Subscribe before reading the snapshot;
payloads are pulled from the inbox. A disconnect or snapshot failure releases
the subscription. The host application owns authentication, origin policy,
request context and server startup.

Legacy wire names remain `origin_canvas_id` and the `canvas` query filter even
for a non-canvas host. They are opaque origin identifiers here. The router has
the same response fields and error status rules as Anchor's existing endpoints.
Body `actor` overrides the request's actor; body `author` never sets authorship.
Use `default_actor` for a host-specific HTTP actor when no context is present.

For MCP, mount `tool_definitions(target_schema=..., op_schema=...)` and dispatch
with `call_tool(service, name, arguments, actor=connected_actor)`. The generic
`intent_ask` takes optional `origin_canvas_id`, `text` and JSON `targets`. Anchor's
wrapper retains `workspace_slug` and its node-ID array and translates the ask.

For CLI, mount `create_cli(lambda: service)` into a Typer application. Its `ask`
uses `--text`, optional `--origin` and `--targets` as a JSON array or `@path`.
Suggestion operations use `--ops` as JSON. This factory does not consult Anchor
configuration or `ANCHOR_AGENT`; Anchor's existing callback retains that policy.

## Persistence and application limits

Targets are detached and checked for strict finite JSON before persistence.
Decoded targets, application operations and undo input are detached before host
calls; returned undo is detached before storing it. Legacy targets and undo
records retain their JSON structure when loaded.

Host application and persistence of the updated thread are separate operations.
A failed thread write after host application does not roll back the host.
Anchor's pre-state snapshot and batch application also remain separate; this
extraction adds no cross-process transaction or lock. Memory count signals only
notify subscribers within the current process.

The independent form-host integration tests in `tests/intent_layer` exercise
all three transports with field IDs and FieldSet operations, without Anchor
canvas commands. Import checks block every Anchor import in fresh interpreters.
Packaging checks build a wheel and source distribution, inspect their members,
and import directly from the wheel with Anchor blocked.
