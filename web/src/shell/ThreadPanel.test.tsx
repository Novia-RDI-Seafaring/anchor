/**
 * ThreadPanel tests (#344) — the docked review surface.
 *
 * Pins the panel contract: items render per type and state, an open
 * question answers through the answer route, a pending suggestion
 * approves / declines (with comment) / comments through the right routes
 * and toggles the ghost preview on click, a stale suggestion is marked and
 * cannot be approved, a result offers the catch-up diff since
 * `base_version`, and the bottom composer adds a human message item.
 */
import { ReactFlowProvider } from "@xyflow/react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as canvasesApi from "@/api/canvases";
import * as intentsApi from "@/api/intents";
import type { Intent } from "@/api/intents";
import { useCanvasStore } from "@/stores/canvasStore";
import { CANVAS_EDGES, CANVAS_NODES, makeFullThread, makeItem, makeThread } from "@/threads/fixtures";
import { useThreadsStore } from "@/threads/threadsStore";

import { ThreadPanel } from "./ThreadPanel";

function mount(thread: Intent) {
  vi.spyOn(intentsApi.intents, "listAll").mockResolvedValue([thread]);
  // The sync GET always serves the pre-action record, like a server that
  // answered before the action's POST: the panel must keep the action's
  // result (the sync drops responses that predate an action).
  vi.spyOn(intentsApi.intents, "get").mockResolvedValue(thread);
  useThreadsStore.setState({ openThreadId: thread.id, thread, previewItemId: null, actionSeq: 0 });
  return render(
    <ReactFlowProvider>
      <ThreadPanel workspaceSlug="plant" />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useCanvasStore.setState({ slug: "plant", nodes: { ...CANVAS_NODES }, edges: { ...CANVAS_EDGES }, version: 22 });
  useThreadsStore.setState({ openThreadId: null, thread: null, previewItemId: null, threadError: null });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ThreadPanel rendering", () => {
  it("renders nothing while no thread is open", () => {
    render(
      <ReactFlowProvider>
        <ThreadPanel workspaceSlug="plant" />
      </ReactFlowProvider>,
    );
    expect(screen.queryByTestId("thread-panel")).toBeNull();
  });

  it("shows the ask, its targets, and every item in order with type-specific chrome", async () => {
    mount(makeFullThread());
    expect(screen.getByTestId("thread-ask").textContent).toContain("make sense of this");
    expect(screen.getByTestId("thread-targets").textContent).toContain("2 targets");
    expect(screen.getByTestId("thread-status").textContent).toBe("open");

    const items = screen.getAllByTestId("thread-item");
    expect(items.map((i) => i.getAttribute("data-item-type"))).toEqual([
      "message",
      "question",
      "suggestion",
      "result",
    ]);
    expect(items[0]!.textContent).toContain("Looking at the two nodes now.");
    expect(items[0]!.textContent).toContain("claude-code");
    // Open question → inline answer box.
    expect(screen.getByTestId("thread-answer-input")).toBeTruthy();
    // Suggestion → rationale, op count, state chip, actions.
    expect(items[2]!.textContent).toContain("Group them under a cooling loop");
    expect(items[2]!.textContent).toContain("5 ops");
    expect(screen.getByTestId("thread-suggestion-state").textContent).toBe("pending");
    expect(items[2]!.getAttribute("data-stale")).toBe("false");
    expect(screen.getByTestId("thread-approve")).toBeTruthy();
    // Result → summary + catch-up entry point.
    expect(items[3]!.textContent).toContain("Grouped and renamed");
    expect(screen.getByTestId("thread-show-changes").textContent).toContain("since v20");
    await waitFor(() => expect(intentsApi.intents.get).toHaveBeenCalledWith("t1"));
  });

  it("renders answered questions and non-pending suggestion states without actions", () => {
    mount(
      makeThread({
        status: "resolved",
        items: [
          makeItem({ id: "q1", type: "question", text: "Main pump?", state: "answered", answer: "Yes." }),
          makeItem({ id: "s1", type: "suggestion", text: "old", state: "superseded", ops: [] }),
          makeItem({ id: "s2", type: "suggestion", text: "declined one", state: "declined", ops: [] }),
          makeItem({
            id: "s3",
            type: "suggestion",
            text: "applied one",
            state: "applied",
            ops: [],
            supersedes: "s1",
            applied_versions: [21, 22],
          }),
        ],
      }),
    );
    expect(screen.getByTestId("thread-status").textContent).toBe("resolved");
    expect(screen.queryByTestId("thread-answer-input")).toBeNull();
    expect(screen.getByTestId("thread-answer-text").textContent).toBe("Yes.");
    expect(screen.getAllByTestId("thread-suggestion-state").map((c) => c.textContent)).toEqual([
      "superseded",
      "declined",
      "applied",
    ]);
    expect(screen.queryByTestId("thread-approve")).toBeNull();
    expect(screen.getByText(/applied as v21, v22/)).toBeTruthy();
    expect(screen.getByText(/revision/)).toBeTruthy();
  });

  it("marks a pending suggestion stale when its ops reference missing elements", () => {
    const { n2: _gone, ...nodes } = CANVAS_NODES;
    useCanvasStore.setState({ nodes });
    mount(makeFullThread());
    const suggestion = screen.getAllByTestId("thread-item")[2]!;
    expect(suggestion.getAttribute("data-stale")).toBe("true");
    expect(screen.getByTestId("thread-suggestion-stale")).toBeTruthy();
    expect((screen.getByTestId("thread-approve") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("thread-decline") as HTMLButtonElement).disabled).toBe(false);
  });

  it("closes from the header", () => {
    mount(makeFullThread());
    fireEvent.click(screen.getByTestId("thread-close"));
    expect(useThreadsStore.getState().openThreadId).toBeNull();
    expect(screen.queryByTestId("thread-panel")).toBeNull();
  });
});

describe("ThreadPanel actions", () => {
  it("clicking a suggestion toggles the ghost preview", () => {
    mount(makeFullThread());
    fireEvent.click(screen.getByTestId("thread-suggestion-toggle"));
    expect(useThreadsStore.getState().previewItemId).toBe("s1");
    expect(screen.getAllByTestId("thread-item")[2]!.getAttribute("data-previewing")).toBe("true");
    fireEvent.click(screen.getByTestId("thread-suggestion-toggle"));
    expect(useThreadsStore.getState().previewItemId).toBeNull();
  });

  it("answers an open question through the answer route", async () => {
    const thread = makeFullThread();
    const answered = makeFullThread({
      items: thread.items!.map((i) =>
        i.id === "q1" ? { ...i, state: "answered" as const, answer: "Yes, P-101." } : i,
      ),
    });
    const answer = vi.spyOn(intentsApi.intents, "answer").mockResolvedValue(answered);
    mount(thread);
    fireEvent.change(screen.getByTestId("thread-answer-input"), { target: { value: "Yes, P-101." } });
    await act(async () => {
      fireEvent.keyDown(screen.getByTestId("thread-answer-input"), { key: "Enter" });
    });
    expect(answer).toHaveBeenCalledWith("t1", "q1", "Yes, P-101.");
    // The returned record lands immediately.
    expect(screen.queryByTestId("thread-answer-input")).toBeNull();
    expect(screen.getByTestId("thread-answer-text").textContent).toBe("Yes, P-101.");
  });

  it("Approve applies the suggestion and clears its preview", async () => {
    const thread = makeFullThread();
    const applied = makeFullThread({
      items: thread.items!.map((i) =>
        i.id === "s1" ? { ...i, state: "applied" as const, applied_versions: [21] } : i,
      ),
    });
    const apply = vi.spyOn(intentsApi.intents, "apply").mockResolvedValue(applied);
    mount(thread);
    fireEvent.click(screen.getByTestId("thread-suggestion-toggle"));
    expect(useThreadsStore.getState().previewItemId).toBe("s1");
    await act(async () => {
      fireEvent.click(screen.getByTestId("thread-approve"));
    });
    expect(apply).toHaveBeenCalledWith("t1", "s1");
    expect(screen.getByTestId("thread-suggestion-state").textContent).toBe("applied");
    expect(useThreadsStore.getState().previewItemId).toBeNull();
  });

  it("Decline sends the optional comment through the decline route", async () => {
    const decline = vi.spyOn(intentsApi.intents, "decline").mockResolvedValue(makeFullThread());
    mount(makeFullThread());
    fireEvent.click(screen.getByTestId("thread-decline"));
    fireEvent.change(screen.getByTestId("thread-decline-comment-input"), {
      target: { value: "keep the pump name" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("thread-decline-comment-submit"));
    });
    expect(decline).toHaveBeenCalledWith("t1", "s1", "keep the pump name");
  });

  it("Decline without a comment sends none", async () => {
    const decline = vi.spyOn(intentsApi.intents, "decline").mockResolvedValue(makeFullThread());
    mount(makeFullThread());
    fireEvent.click(screen.getByTestId("thread-decline"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("thread-decline-comment-submit"));
    });
    expect(decline).toHaveBeenCalledWith("t1", "s1", undefined);
  });

  it("Comment on a suggestion and the bottom composer both add a message item", async () => {
    const addItem = vi.spyOn(intentsApi.intents, "addItem").mockResolvedValue(makeFullThread());
    mount(makeFullThread());

    fireEvent.click(screen.getByTestId("thread-comment"));
    fireEvent.change(screen.getByTestId("thread-suggestion-comment-input"), {
      target: { value: "can you keep the edge?" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("thread-suggestion-comment-submit"));
    });
    expect(addItem).toHaveBeenCalledWith("t1", { type: "message", text: "can you keep the edge?" });

    fireEvent.change(screen.getByTestId("thread-composer-input"), { target: { value: "thanks" } });
    await act(async () => {
      fireEvent.keyDown(screen.getByTestId("thread-composer-input"), { key: "Enter" });
    });
    expect(addItem).toHaveBeenLastCalledWith("t1", { type: "message", text: "thanks" });
    expect((screen.getByTestId("thread-composer-input") as HTMLTextAreaElement).value).toBe("");
  });

  it("surfaces an action failure inline", async () => {
    vi.spyOn(intentsApi.intents, "apply").mockRejectedValue(new Error("node n2 no longer exists"));
    mount(makeFullThread());
    await act(async () => {
      fireEvent.click(screen.getByTestId("thread-approve"));
    });
    expect(screen.getByTestId("thread-action-error").textContent).toContain("n2 no longer exists");
  });

  it("'show what changed' fetches the catch-up diff since base_version", async () => {
    const changes = vi.spyOn(canvasesApi.canvases, "changes").mockResolvedValue({
      from_version: 20,
      to_version: 22,
      groups: [
        {
          actor: { kind: "agent", label: "claude-code" },
          nodes_added: [{ id: "n9", label: "Cooling loop", node_type: "concept" }],
          nodes_updated: [{ id: "n1", label: "Pump P-101", node_type: "spec" }],
          nodes_removed: [],
          edges_added: [],
          edges_updated: [],
          edges_removed: [],
        },
      ],
    });
    mount(makeFullThread());
    await act(async () => {
      fireEvent.click(screen.getByTestId("thread-show-changes"));
    });
    expect(changes).toHaveBeenCalledWith("plant", 20);
    const diff = screen.getByTestId("thread-changes");
    expect(diff.textContent).toContain("v20 → v22");
    expect(diff.textContent).toContain("claude-code");
    expect(diff.textContent).toContain("Cooling loop");
    expect(diff.textContent).toContain("Pump P-101");
  });
});
