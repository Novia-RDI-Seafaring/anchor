# Plain DOM intent example

This ordinary React form mounts the reusable intent overlay without Anchor
contexts, stores, API clients, or ReactFlow. Its host owns field identities,
DOM geometry, transport, and inert previews of the backend's `FieldSet` patches.

Start the [form backend](../../../examples/intent-layer/README.md) from the
repository root, then start this separate frontend from `web`:

```sh
pnpm exec vite --config vite.intent-example.config.ts
```

Open <http://127.0.0.1:5193/examples/intent-layer/index.html>. Both servers bind
to loopback; Vite proxies `/form` to port 8003. The backend keeps its demo state
in memory and resets on restart. Replies are fixed fixtures, with no AI provider.

1. Click **Mark up fields**, draw across either field, then double-click nearby
   to write. Press Enter and send the remark.
2. Click **Demo reply to sent remarks**. Answer the question, inspect the inert
   field previews, and approve. The backend changes the real form values.
3. Click **put it back** to restore the original values through the backend.

**Capture field crop** optionally opens the browser's screen-sharing picker.
Choose this browser tab. The host crops a real video frame to the visible field
boxes, encodes PNG pixels, and immediately stops every capture track. Window or
monitor capture is rejected. Denial, unavailable APIs, offscreen fields, or
capture errors leave the remark usable with IDs and geometry alone. Keep the
fields visible while capturing. A capture is attached to the next successful
remark and then cleared.

Stable `data-intent-id` attributes define identity. Development builds optionally
include component/source diagnostics from React's private Fiber metadata; missing
metadata falls back to DOM labels and boxes. Production builds omit those
diagnostics. Private Fiber metadata is a prototype aid, not a supported identity
contract. The generic overlay never interprets screenshot pixels or field patches.

Validation includes crop scaling/clipping, capture denial and track cleanup,
metadata fallback, transport and subscription cleanup, strict TypeScript, and a
standalone build that rejects Anchor imports. Real browser validation exercised
physical drawing/submission and an actual browser PNG crop through the mounted
backend's question, approve, and revert lifecycle. That crop came from browser
automation's tab screenshot API; the native screen-sharing picker was not driven
end to end by automation.

```sh
pnpm test src/examples/intent-layer
pnpm exec tsc --noEmit -p tsconfig.intent-example.json
pnpm exec vite build --config vite.intent-example.config.ts
```
