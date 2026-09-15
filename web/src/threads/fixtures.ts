/**
 * Test fixtures for scoped-ask threads (#344), shaped exactly per the
 * contract in docs/proposals/scoped-ask-threads.md so the web tests pin the
 * wire shape the backend (#343) is built against. Not imported by app code.
 */
import type { Intent, ThreadItem, ThreadOp } from "@/api/intents";

export const AGENT = { kind: "agent", label: "claude-code" } as const;
export const HUMAN = { kind: "human", label: "browser" } as const;

export function makeItem(over: Partial<ThreadItem> & { id: string }): ThreadItem {
  return {
    type: "message",
    author: AGENT,
    text: "",
    created_at: 1789453960 + Number(over.id.replace(/\D/g, "") || 0),
    state: null,
    ...over,
  };
}

/** The ops of a typical "name and group" suggestion: one added node with a
 *  client id, an edge to it, a label update, and a removal. */
export const SUGGESTION_OPS: ThreadOp[] = [
  {
    type: "NodeAdded",
    payload: { id: "tmp-1", node_type: "concept", label: "Cooling loop", x: 400, y: 40, data: {} },
  },
  { type: "EdgeAdded", payload: { source: "n1", target: "tmp-1", edge_type: "floating", data: {} } },
  { type: "NodeUpdated", payload: { id: "n1", fields: { label: "Pump P-101" } } },
  { type: "NodeRemoved", payload: { id: "n2" } },
  { type: "EdgeRemoved", payload: { id: "e1" } },
];

export function makeThread(over: Partial<Intent> = {}): Intent {
  return {
    id: "t1",
    kind: "user_request",
    origin_canvas_id: "plant",
    target: null,
    targets: [
      { workspace_id: "plant", node_id: "n1" },
      { workspace_id: "plant", node_id: "n2" },
    ],
    base_version: 20,
    payload: { text: "make sense of this" },
    status: "pending",
    created_at: 1789453900,
    items: [],
    ...over,
  };
}

/** A thread with one of every item type in a realistic order. */
export function makeFullThread(over: Partial<Intent> = {}): Intent {
  return makeThread({
    items: [
      makeItem({ id: "m1", type: "message", text: "Looking at the two nodes now.", created_at: 1789453961 }),
      makeItem({ id: "q1", type: "question", text: "Is P-101 the main pump?", state: "open", created_at: 1789453962 }),
      makeItem({
        id: "s1",
        type: "suggestion",
        text: "Group them under a cooling loop and rename the pump.",
        state: "pending",
        ops: SUGGESTION_OPS,
        created_at: 1789453963,
      }),
      makeItem({
        id: "r1",
        type: "result",
        text: "Grouped and renamed; one edge dropped.",
        created_at: 1789453964,
      }),
    ],
    ...over,
  });
}

/** Canvas nodes / edges the fixtures reference. */
export const CANVAS_NODES = {
  n1: { id: "n1", node_type: "spec", label: "Pump", x: 10, y: 20, width: 100, height: 50, data: {} },
  n2: { id: "n2", node_type: "document", label: "Datasheet", x: 200, y: 120, width: 80, height: 40, data: {} },
  n3: { id: "n3", node_type: "chart", label: "Curve", x: 500, y: 500, data: {} },
};

export const CANVAS_EDGES = {
  e1: { id: "e1", source: "n1", target: "n2", label: "", edge_type: "floating", data: {} },
};
