/**
 * intents API tests (#344) — the thread contract at the wire.
 *
 * Pins the exact request shapes the backend (#343) is built against:
 * `POST /api/intents` with `targets[]`, the items / answer / apply /
 * decline routes, and the tolerant envelope handling (`{intent}` or a bare
 * record). Every mutate fires the same-window changed nudge.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";
import { INTENTS_CHANGED_EVENT, intents } from "./intents";

vi.mock("./client", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  BACKEND_URL: "",
}));

const record = {
  id: "t1",
  kind: "user_request",
  origin_canvas_id: "plant",
  target: null,
  targets: [{ workspace_id: "plant", node_id: "n1" }],
  base_version: 20,
  payload: { text: "make sense of this" },
  status: "pending",
  created_at: 1,
  items: [],
};

let nudges = 0;
const onChanged = () => {
  nudges += 1;
};

beforeEach(() => {
  nudges = 0;
  window.addEventListener(INTENTS_CHANGED_EVENT, onChanged);
  vi.mocked(api.post).mockReset();
  vi.mocked(api.get).mockReset();
});

afterEach(() => {
  window.removeEventListener(INTENTS_CHANGED_EVENT, onChanged);
});

describe("intents.ask", () => {
  it("posts a user_request with the selection as targets and {text} payload", async () => {
    vi.mocked(api.post).mockResolvedValue({ intent: record });
    const out = await intents.ask({
      text: "make sense of this",
      workspaceSlug: "plant",
      nodeIds: ["n1", "n2"],
    });
    expect(api.post).toHaveBeenCalledWith("/api/intents", {
      kind: "user_request",
      origin_canvas_id: "plant",
      targets: [
        { workspace_id: "plant", node_id: "n1" },
        { workspace_id: "plant", node_id: "n2" },
      ],
      payload: { text: "make sense of this" },
    });
    expect(out.id).toBe("t1");
    expect(nudges).toBe(1);
  });

  it("accepts a bare record as the response", async () => {
    vi.mocked(api.post).mockResolvedValue(record);
    const out = await intents.ask({ text: "x", workspaceSlug: "plant", nodeIds: ["n1"] });
    expect(out.id).toBe("t1");
  });

  it("surfaces a server error message", async () => {
    vi.mocked(api.post).mockResolvedValue({ error: "unknown_target", message: "n9 not found" });
    await expect(
      intents.ask({ text: "x", workspaceSlug: "plant", nodeIds: ["n9"] }),
    ).rejects.toThrow("n9 not found");
    expect(nudges).toBe(0);
  });
});

describe("thread reads and item routes", () => {
  it("get reads one full record", async () => {
    vi.mocked(api.get).mockResolvedValue({ intent: record });
    expect((await intents.get("t1")).targets).toHaveLength(1);
    expect(api.get).toHaveBeenCalledWith("/api/intents/t1");
  });

  it("addItem posts {type, text} and only includes ops / supersedes when given", async () => {
    vi.mocked(api.post).mockResolvedValue({ intent: record });
    await intents.addItem("t1", { type: "message", text: "hi" });
    expect(api.post).toHaveBeenLastCalledWith("/api/intents/t1/items", {
      type: "message",
      text: "hi",
    });
    await intents.addItem("t1", {
      type: "suggestion",
      text: "rationale",
      ops: [{ type: "NodeRemoved", payload: { id: "n2" } }],
      supersedes: "s0",
    });
    expect(api.post).toHaveBeenLastCalledWith("/api/intents/t1/items", {
      type: "suggestion",
      text: "rationale",
      ops: [{ type: "NodeRemoved", payload: { id: "n2" } }],
      supersedes: "s0",
    });
    expect(nudges).toBe(2);
  });

  it("answer posts {text} to the item's answer route", async () => {
    vi.mocked(api.post).mockResolvedValue({ intent: record });
    await intents.answer("t1", "q1", "yes, the main pump");
    expect(api.post).toHaveBeenCalledWith("/api/intents/t1/items/q1/answer", {
      text: "yes, the main pump",
    });
  });

  it("apply posts an empty body to the item's apply route", async () => {
    vi.mocked(api.post).mockResolvedValue({ intent: record });
    await intents.apply("t1", "s1");
    expect(api.post).toHaveBeenCalledWith("/api/intents/t1/items/s1/apply", {});
  });

  it("apply surfaces the failing op reason", async () => {
    vi.mocked(api.post).mockResolvedValue({
      error: "stale",
      failing_op_index: 2,
      reason: "node n2 no longer exists",
    });
    await expect(intents.apply("t1", "s1")).rejects.toThrow("node n2 no longer exists");
  });

  it("decline posts {comment} only when a comment is given", async () => {
    vi.mocked(api.post).mockResolvedValue({ intent: record });
    await intents.decline("t1", "s1");
    expect(api.post).toHaveBeenLastCalledWith("/api/intents/t1/items/s1/decline", {});
    await intents.decline("t1", "s1", "  not this way  ");
    expect(api.post).toHaveBeenLastCalledWith("/api/intents/t1/items/s1/decline", {
      comment: "not this way",
    });
  });
});
