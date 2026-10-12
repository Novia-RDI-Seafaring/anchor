# Intent layer as a reusable module

Status: Proposed. References #413.

The approved starting direction is staged prerequisite work, then extraction
using React and a mounted FastAPI router, preserving typed Anchor commands.
This proposal records the implementation seams and review gates. Package
naming, publication and a separate server process remain undecided.

## Current state and prerequisite assessment

Issue #413 specifies #407, #408 and #409 as prerequisites. At the start of
this work all three remain open. The overlay must be tested and split before
it is extracted.

The thread module already has depth: durable queue and thread transitions,
placed status, questions, suggestions, timing and count signals share one
IntentService interface used by HTTP, MCP and CLI. Its implementation imports
WorkspaceService and BatchApplyError directly. Targets are validated as
workspace_id/node_id pairs; operation validation uses SUGGESTION_OP_TYPES.
The apply path snapshots state, runs apply_batch, computes inverse commands,
persists the undo, then signals. Revert uses apply_batch(restore=True).
These dependencies are visible in src/anchor/core/services/intent_service.py.
ProjectRuntime constructs the module with the filesystem store, bus, clock and
workspace in src/anchor/adapters/project_runtime.py.

The overlay still obtains ReactFlow transforms and viewport control directly,
reads canvas nodes and edges from useCanvasStore, reads rendered row positions
and sampled edge paths from ReactFlow DOM, and files through Anchor adapters.
See web/src/canvas/CommentLasso.tsx, particularly rowsOf and edgesOf.
The three callbacks proposed by #413 cover target geometry, but the existing
edge gestures and viewport behavior require explicit ownership too. Extracting
now would carry hidden Anchor dependencies into the purportedly generic module.

## Starting defaults

- Keep React for the first overlay module. Anchor already uses React, and a
  framework-free renderer creates additional behavior to verify without a
  second host yet.
- Mount the thread transport as a FastAPI router in the existing process first.
  Keep project runtime composition, stores and event delivery local. A separate
  process would add deployment and cross-process consistency requirements.
- Preserve Anchor's typed commands and wire format initially. Let an Anchor
  adapter own command validation, state lookup, application, inverse generation
  and restoration. Opaque payloads need a documented host validation interface
  before they can be accepted.
- Preserve current HTTP/MCP/CLI names, errors, actor/approver/causation attribution,
  project queue scope, count-only push signals, timing, and legacy persistence.
  Opaque internal target ids can be translated at the Anchor adapter; do not
  silently rewrite persisted targets or undo_ops.

## Smallest first deliverable

A behavior-preserving thread host interface in Anchor, following the
prerequisite sequence. Keep package publication and the overlay out of
this first PR. The interface should allow a host to apply commands and return
an undo record plus existing result metadata, and revert that undo record.
It must carry scope, actor, approver and causation context; bare apply(ops) is
insufficient to preserve today's interface invariants.

Implement the Anchor adapter using the existing workspace batch and inverse
logic. Exercise the thread module through its public interface with a small
in-memory host adapter as the second adapter, plus end-to-end Anchor apply and
revert regressions. This establishes a real seam before adding a package.
Keep all adapters behavior-compatible; no new operation is needed.

The host must either capture pre-state and apply under one workspace mutation
lock, or document current concurrency constraints rather than claim atomic
undo across multiple processes. The existing get_state then apply_batch path
is not evidence of one atomic snapshot-and-apply transaction. Preserve honest
failure outcomes if storage of the thread undo fails after canvas application.

## Delivery sequence and review gates

1. #407: pin overlay interactions, coordinate transforms, gesture resolution,
   submission and cancellation. Verify public behavior before restructuring.
2. #408: move overlay state behind named actions, preserving the #407 tests.
3. #409: split interaction, rendering and host lookups into focused modules.
   Keep ReactFlow DOM reads in the Anchor adapter.
4. Thread host interface and Anchor adapter, with compatibility and undo tests.
5. Standalone thread package and mounted router, plus HTTP/MCP/CLI parity.
6. React overlay interface with getBoxes, rowsOf and screenToWorld; explicitly
   settle edge-path sampling, viewport controls, submission and display of
   thread items rather than hiding extra dependencies in global stores.
7. One small DOM-host prototype. Use stable data-intent-id attributes, identity
   coordinates and development-only source metadata. React fiber inspection is
   version-sensitive; missing component/source metadata must degrade gracefully.
   Screenshot crops and patch approval/revert remain host responsibilities.

Each stage is independently reviewable, passes relevant existing tests, and
has no behavior change until the DOM prototype. Package extraction is gated on
Anchor compatibility and a genuinely independent second adapter. Do not build
a new package interface for every existing internal helper.

## Decisions still open

The thread host-interface PR is the first extraction deliverable; #407 is the
first prerequisite implementation task. Each milestone gets its own focused
PR. The proposal does not itself complete #413.

Before extracting the overlay, settle ownership of edge paths, viewport
controls, submission and thread display. The three-callback geometry interface
is incomplete for today's behavior until these responsibilities have a home.

Before making commands opaque, document host validation, operation errors and
undo persistence. Keep arbitrary executable payloads out of the thread module.

Before publishing a package, settle its name, compatibility policy and packaging
with an independent host. A framework-free renderer and a standalone daemon are
future alternatives, not commitments of this proposal.
