# React intent overlay

This internal React module mounts onto an ordinary positioned DOM host. Import
`IntentOverlay` and the public types from `index.ts`. The entry also imports
the explicit, scoped `styles.css`; it needs no Anchor stylesheet or Tailwind
runtime. React 19 and Zustand 5 are its runtime dependencies. No separate npm
distribution is published.

```tsx
import { IntentOverlay, type OverlayHost } from "./intent-overlay";

function ReviewSurface({ host }: { host: OverlayHost }) {
  return <div style={{ position: "relative", width: 1000, height: 800 }}>
    <YourHostContent />
    <IntentOverlay active host={host} />
  </div>;
}
```

The host supplies measured boxes, row bands, sampled edge paths, the current
viewport and screen-to-world conversion. Boxes and drawing metadata use host
world coordinates. The viewport maps world coordinates into the positioned
host surface; screen conversion accounts for the surface's screen offset.
IDs are opaque strings, including strings containing slashes or colons.

Keep `host.thread` stable for the mounted host scope. It owns initial scoped
loading, submission, thread mutations and a change subscription with cleanup.
The overlay polls filed threads and cancels refresh results after cleanup.
Its store belongs to one mount; disabling `active` pauses transient gestures
while retaining ink, shelf and filed history. Unmounting ends that lifetime.

`display.preview` produces inert boxes, rows and resolved edge endpoints.
The renderer never interprets operations or writes host state during preview.
Approve, decline and revert call the thread port. The host/backend validates
and performs the change, and owns exact undo behavior.

With Space held, overlay content releases pointer hits. The optional input
policy decides whether an underlying press starts host panning. A form can
omit the policy so fields and links keep their normal behavior. Global cursor
flags and selectors for host elements belong in the host adapter.

Anchor's adapter is `canvas/markup/AnchorHost.ts`. It preserves existing
workspace/node target pairs, public HTTP requests, preview command semantics,
ReactFlow viewport controls and source-anchor hit policy. Compatibility
exports preserve the existing geometry/store imports and interaction tests.

From `web/`, regenerate the standalone stylesheet with
`node scripts/build-intent-overlay-css.mjs`. It compiles only this module's
utility classes and scopes selectors under `data-intent-overlay`, without
global preflight. Commit the generated stylesheet with markup changes.

Run `node node_modules/vite/bin/vite.js build --config
vite.intent-overlay.config.ts` to build the independent renderer and CSS into
`dist/intent-overlay/`. That build rejects Anchor imports and has no Anchor
alias. Consumers of the build import `index.js` and `styles.css` explicitly.
The ordinary form interaction test mounts without application providers and
fails if an Anchor API, canvas store or ReactFlow import occurs. It proves
state and callback behavior; browser hit testing remains a browser check.
