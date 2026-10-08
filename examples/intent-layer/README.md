# Independent form backend

From the repository root after `uv sync --extra dev`:

```sh
uv run python examples/intent-layer/form_backend.py
```

The server binds only `127.0.0.1:8003`. Set `--port` to choose another port.
This example imports `intent_layer`, not Anchor. It owns an ordinary signup
form with opaque field IDs `email` and `max_flow`:

- `GET /form/state` returns the fields and host revision.
- `/form/inbox` mounts the reusable HTTP inbox, including count-only SSE.
- `POST /form/demo-reply/{intent_id}` authors a question and a fixed proposal.

Create a `user_request` with `origin_canvas_id: "signup"` and the selected
field IDs in `targets`. The legacy origin field name is retained by the shared
wire format. Request payloads, including screenshots and optional DOM metadata,
are stored as opaque data. The backend does not reconstruct or generate images.

The demo reply is explicitly a fixed fixture, not a model invocation. It
proposes `work@example.test` for email and `99.0` for maximum flow. Answer its
question with `{text: "Yes"}`, then apply the suggestion through the inbox.
Revert uses recorded inverse FieldSet operations to restore the previous values.
The host validates the entire batch before changing its fields. Email requires
text; maximum flow requires a finite nonnegative number, excluding booleans.
Operations must stay within the thread's selected signup fields.

State and threads are in memory and reset when the process restarts. Host state
mutation and thread persistence are separate operations; this is not a database
transaction or a production multi-process server. Use the frontend example's
Vite proxy for `/form`; this backend does not expose an unrestricted CORS policy.
