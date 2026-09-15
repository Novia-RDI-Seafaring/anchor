import { api } from "./client";

/**
 * The project-level intents queue API (#148 backend, #323 web surface),
 * extended with scoped-ask threads (#343 backend, #344 web).
 *
 * Wraps the same HTTP endpoints the MCP / CLI adapters mirror:
 *   - `GET  /api/intents`              -> pending intents (oldest first)
 *   - `GET  /api/intents/all`          -> every intent (newest first)
 *   - `GET  /api/intents/{id}`         -> one full record incl. thread items
 *   - `POST /api/intents`              -> enqueue one (optionally with targets)
 *   - `POST /api/intents/{id}/resolve` -> mark one resolved with a result
 *   - `POST /api/intents/{id}/items`                  -> append a thread item
 *   - `POST /api/intents/{id}/items/{item}/answer`    -> answer a question
 *   - `POST /api/intents/{id}/items/{item}/apply`     -> apply a suggestion
 *   - `POST /api/intents/{id}/items/{item}/decline`   -> decline a suggestion
 *
 * `create` authors the panel's free-text `user_request` kind: the payload
 * carries `{text}` plus, when the user attaches the selected canvas node as
 * the target, the same `{workspace_id, node_id}` node-ref shape
 * `drop_to_ingest` uses. `ask` is the scoped form: the selection rides as
 * `targets[]` on the intent itself (the thread contract), and the server
 * records `base_version`.
 *
 * Contract: docs/proposals/scoped-ask-threads.md. The web client is built
 * against that contract, not against a live server, so the response
 * envelopes are read tolerantly: `{intent: …}` (the shape `create` already
 * uses) or a bare record both unwrap to an `Intent`.
 */

export type IntentKind =
  | "drop_to_ingest"
  | "make_reference"
  | "attach_to_fact"
  | "user_request";

/** One targeted canvas element — the node-ref shape shared with payloads. */
export type ThreadTarget = { workspace_id: string; node_id: string };

/** Mirrors the event `Actor`; never client-supplied. */
export type ThreadAuthor = {
  kind: "human" | "agent" | "system";
  label?: string | null;
};

export type ThreadItemType = "message" | "question" | "suggestion" | "result";

export type QuestionState = "open" | "answered";
export type SuggestionState = "pending" | "applied" | "declined" | "superseded";

/**
 * A staged canvas change. Reuses the canvas event vocabulary so apply needs
 * no new mutation code. A `NodeAdded` op may carry a client id (any string)
 * that later ops in the same batch reference; apply maps it to a real id.
 */
export type ThreadOp =
  | { type: "NodeAdded"; payload: { id?: string; node_type?: string; label?: string; x?: number; y?: number; width?: number | null; height?: number | null; data?: Record<string, unknown> } }
  | { type: "NodeUpdated"; payload: { id: string; fields: Record<string, unknown> } }
  | { type: "NodeRemoved"; payload: { id: string } }
  | { type: "EdgeAdded"; payload: { id?: string; source: string; target: string; edge_type?: string; label?: string; data?: Record<string, unknown> } }
  | { type: "EdgeUpdated"; payload: { id: string; fields: Record<string, unknown> } }
  | { type: "EdgeRemoved"; payload: { id: string } };

export type ThreadOpType = ThreadOp["type"];

/** One entry in a thread. `state` is per type: message/result null,
 *  question open|answered, suggestion pending|applied|declined|superseded. */
export type ThreadItem = {
  id: string;
  type: ThreadItemType | (string & {});
  author: ThreadAuthor;
  text: string;
  created_at: number;
  state?: QuestionState | SuggestionState | null;
  /** question only, set when answered */
  answer?: string | null;
  /** suggestion only */
  ops?: ThreadOp[];
  /** suggestion only: a revision of an earlier suggestion */
  supersedes?: string | null;
  /** suggestion only, after apply */
  applied_versions?: number[];
};

/** Mirrors the server's `Intent.to_dict()` (thread fields are additive). */
export type Intent = {
  id: string;
  kind: IntentKind | (string & {});
  origin_canvas_id: string | null;
  target: string | null;
  payload: Record<string, unknown>;
  status: "pending" | "resolved" | (string & {});
  created_at: number;
  resolved_at?: number;
  result?: Record<string, unknown>;
  /** Scoped ask: the selection the thread is anchored to. */
  targets?: ThreadTarget[];
  /** Canvas version when the ask was made. */
  base_version?: number;
  /** Append-only, ordered by created_at. */
  items?: ThreadItem[];
};

/**
 * Browser event dispatched after any intent mutate in this window (create
 * from the panel, dismiss, thread actions). A UI-only nudge — same pattern
 * as `anchor:references-changed` — so the panel refetches immediately
 * without waiting for the SSE signal or the poll.
 */
export const INTENTS_CHANGED_EVENT = "anchor:intents-changed";

export function emitIntentsChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INTENTS_CHANGED_EVENT));
}

type Envelope = Record<string, unknown> & {
  intent?: Intent;
  item?: ThreadItem;
  error?: string;
  message?: string;
  reason?: string;
  failing_op_index?: number;
};

/** Read an `Intent` out of a response: `{intent}` or a bare record. */
function unwrapIntent(res: Envelope | Intent | undefined, what: string): Intent {
  if (res && typeof res === "object") {
    const env = res as Envelope;
    if (env.intent && typeof env.intent === "object") return env.intent;
    if (typeof (res as Intent).id === "string" && "payload" in res) return res as Intent;
    // Prefer the human-readable fields over the error code.
    const detail = [env.message, env.reason, env.error].find(
      (v) => typeof v === "string" && v,
    );
    if (detail) throw new Error(String(detail));
  }
  throw new Error(`${what} failed`);
}

export const intents = {
  listPending: async () =>
    (await api.get<{ intents: Intent[]; count: number }>("/api/intents")).intents,
  listAll: async () =>
    (await api.get<{ intents: Intent[] }>("/api/intents/all")).intents,
  /** One full record, including thread `items` and `targets`. */
  get: async (id: string): Promise<Intent> =>
    unwrapIntent(await api.get<Envelope | Intent>(`/api/intents/${id}`), "intent get"),
  create: async (body: {
    text: string;
    workspaceSlug: string;
    nodeId?: string | null;
  }): Promise<Intent> => {
    const payload: Record<string, unknown> = { text: body.text };
    if (body.nodeId) {
      payload.workspace_id = body.workspaceSlug;
      payload.node_id = body.nodeId;
    }
    const res = await api.post<{ intent?: Intent; error?: string; message?: string }>(
      "/api/intents",
      {
        kind: "user_request",
        origin_canvas_id: body.workspaceSlug,
        payload,
      },
    );
    if (!res.intent) throw new Error(res.message ?? res.error ?? "intent create failed");
    emitIntentsChanged();
    return res.intent;
  },
  /**
   * Scoped ask (#344): a `user_request` anchored to the selected nodes.
   * `targets` = `{workspace_id, node_id}` per selected node; the server
   * records `base_version` from the origin canvas.
   */
  ask: async (body: {
    text: string;
    workspaceSlug: string;
    nodeIds: string[];
  }): Promise<Intent> => {
    const res = await api.post<Envelope | Intent>("/api/intents", {
      kind: "user_request",
      origin_canvas_id: body.workspaceSlug,
      targets: body.nodeIds.map((node_id) => ({
        workspace_id: body.workspaceSlug,
        node_id,
      })),
      payload: { text: body.text },
    });
    const intent = unwrapIntent(res, "intent ask");
    emitIntentsChanged();
    return intent;
  },
  resolve: async (id: string, result?: Record<string, unknown>) => {
    const res = await api.post<{ resolved?: Intent; error?: string }>(
      `/api/intents/${id}/resolve`,
      result !== undefined ? { result } : {},
    );
    if (!res.resolved) throw new Error(res.error ?? "intent resolve failed");
    emitIntentsChanged();
    return res.resolved;
  },
  /** Append a thread item. The browser only authors `message` items
   *  (comments); agents post questions / suggestions / results. */
  addItem: async (
    id: string,
    body: { type: ThreadItemType; text: string; ops?: ThreadOp[]; supersedes?: string },
  ): Promise<Intent> => {
    const payload: Record<string, unknown> = { type: body.type, text: body.text };
    if (body.ops) payload.ops = body.ops;
    if (body.supersedes) payload.supersedes = body.supersedes;
    const intent = unwrapIntent(
      await api.post<Envelope | Intent>(`/api/intents/${id}/items`, payload),
      "intent add item",
    );
    emitIntentsChanged();
    return intent;
  },
  /** Answer an open question item. */
  answer: async (id: string, itemId: string, text: string): Promise<Intent> => {
    const intent = unwrapIntent(
      await api.post<Envelope | Intent>(`/api/intents/${id}/items/${itemId}/answer`, { text }),
      "intent answer",
    );
    emitIntentsChanged();
    return intent;
  },
  /** Apply a pending suggestion's ops atomically (agent as actor). A
   *  validation failure surfaces as an Error carrying the server's reason. */
  apply: async (id: string, itemId: string): Promise<Intent> => {
    const intent = unwrapIntent(
      await api.post<Envelope | Intent>(`/api/intents/${id}/items/${itemId}/apply`, {}),
      "intent apply",
    );
    emitIntentsChanged();
    return intent;
  },
  /** Decline a pending suggestion; the comment (if any) lands as a
   *  message item. */
  decline: async (id: string, itemId: string, comment?: string): Promise<Intent> => {
    const trimmed = comment?.trim();
    const intent = unwrapIntent(
      await api.post<Envelope | Intent>(
        `/api/intents/${id}/items/${itemId}/decline`,
        trimmed ? { comment: trimmed } : {},
      ),
      "intent decline",
    );
    emitIntentsChanged();
    return intent;
  },
};
