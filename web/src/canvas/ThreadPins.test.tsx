/**
 * ThreadPins tests (#344) — overlay markers for open threads.
 *
 * Pins: a marker lands at the top-right of the thread's targets on this
 * canvas, threads sharing an anchor collapse into one marker with a count
 * badge (click → picker), a single-thread marker opens the thread on
 * click, and nothing renders for resolved / foreign / target-less threads.
 * The list arrives through the shared intents feed, so the feed's fetch
 * is stubbed to return the seeded threads.
 */
import { ReactFlowProvider } from "@xyflow/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as intentsApi from "@/api/intents";
import type { Intent } from "@/api/intents";
import { useIntentsFeedStore } from "@/shell/intentsFeed";
import { useCanvasStore } from "@/stores/canvasStore";
import { CANVAS_NODES, makeThread } from "@/threads/fixtures";
import { useThreadsStore } from "@/threads/threadsStore";

import { ThreadPins } from "./ThreadPins";

function mount(threads: Intent[]) {
  vi.spyOn(intentsApi.intents, "listAll").mockResolvedValue(threads);
  useIntentsFeedStore.setState({ items: threads, error: null, tick: 0 });
  return render(
    <ReactFlowProvider>
      <ThreadPins workspaceSlug="plant" />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useCanvasStore.setState({ nodes: { ...CANVAS_NODES } });
  useThreadsStore.setState({ openThreadId: null, thread: null, previewItemId: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  useIntentsFeedStore.setState({ items: [], error: null, tick: 0 });
});

describe("ThreadPins", () => {
  it("places one marker at the top-right of the targets' bounding box", async () => {
    mount([makeThread()]);
    const pin = await screen.findByTestId("thread-pin");
    expect(pin.style.left).toBe("280px");
    expect(pin.style.top).toBe("20px");
    expect(pin.getAttribute("data-count")).toBe("1");
    expect(screen.queryByTestId("thread-pin-count")).toBeNull();
  });

  it("opens the thread on click", async () => {
    mount([makeThread({ payload: { text: "compare these" } })]);
    const pin = await screen.findByTestId("thread-pin");
    fireEvent.click(pin.querySelector("button")!);
    expect(useThreadsStore.getState().openThreadId).toBe("t1");
  });

  it("collapses threads sharing an anchor into a counted marker with a picker", async () => {
    mount([
      makeThread({ id: "a", created_at: 1, payload: { text: "first ask" } }),
      makeThread({ id: "b", created_at: 2, payload: { text: "second ask" } }),
    ]);
    const pin = await screen.findByTestId("thread-pin");
    expect(screen.getAllByTestId("thread-pin")).toHaveLength(1);
    expect(screen.getByTestId("thread-pin-count").textContent).toBe("2");
    expect(pin.getAttribute("data-thread-ids")).toBe("a,b");

    fireEvent.click(pin.querySelector("button")!);
    expect(useThreadsStore.getState().openThreadId).toBeNull();
    const picker = screen.getByTestId("thread-pin-picker");
    fireEvent.click(picker.querySelector("button:nth-child(2)")!);
    expect(useThreadsStore.getState().openThreadId).toBe("b");
    expect(screen.queryByTestId("thread-pin-picker")).toBeNull();
  });

  it("renders nothing for resolved, foreign, or target-less intents", async () => {
    mount([
      makeThread({ id: "done", status: "resolved" }),
      makeThread({ id: "elsewhere", targets: [{ workspace_id: "other", node_id: "n1" }] }),
      makeThread({ id: "plain", targets: undefined }),
    ]);
    await waitFor(() => expect(intentsApi.intents.listAll).toHaveBeenCalled());
    expect(screen.queryByTestId("thread-pin")).toBeNull();
  });

  it("follows the workspace store: a pin vanishes when its targets are removed", async () => {
    mount([makeThread()]);
    await screen.findByTestId("thread-pin");
    useCanvasStore.setState({ nodes: {} });
    await waitFor(() => expect(screen.queryByTestId("thread-pin")).toBeNull());
  });
});
