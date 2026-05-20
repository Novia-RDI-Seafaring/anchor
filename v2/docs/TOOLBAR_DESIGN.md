# Toolbar Design — Why a Side Rail?

The shell currently has a left-side rail (Palette + Library) instead of a
floating top toolbar. Was that intentional? Reading the code, yes — and the
reason becomes visible the moment you look at what the rail actually
contains.

## Three bullets

- **The rail hosts list content, not just buttons.** `Library.tsx` browses
  ingested documents and CAD models — a scrollable, polling-refreshed,
  filterable list of draggable items. That kind of content needs vertical
  space and a stable hit target you can drag from. A horizontal top
  toolbar is fine for icon commands, but it can't host "all documents in
  the workspace" without becoming a dropdown — which kills the drag
  affordance that's central to Anchor's workflow (drop a document onto
  the canvas, drop a shape onto the canvas).

- **Tradeoff.** A side rail eats ~240 px of horizontal canvas room in
  exchange for wide, stable drag targets and obvious tab structure. A
  floating toolbar gives the canvas more screen, but lists either become
  cramped popovers or get exiled to a separate window. For an
  engineering canvas where the user is mostly placing and wiring nodes —
  not zooming into a single artefact — the wider canvas isn't worth the
  list-affordance cost.

- **The middle ground (what we just shipped).** The rail is now
  collapsible. Expanded, it behaves as before. Collapsed, it shrinks to a
  ~40 px icon strip where the category glyphs are still clickable —
  pressing one expands the rail into that tab. So in the steady state the
  rail is effectively a thin floating-toolbar-like strip, and the full
  panel only appears when the user actually needs the list. Shortcut:
  `[`. Preference is persisted via `useUiStore.leftRailCollapsed`.

## Other notes

- The monitor route (`/m/:id`) deliberately has no shell — it's the
  read-only projection used by the snapshotter and XR overlays. The
  toolbar discussion only applies to `/c/:id`.
- A future "floating command bar" (think: command palette + recent
  actions) is still possible on top of this, layered over the canvas.
  The rail collapse makes that easier, not harder — they're orthogonal.
