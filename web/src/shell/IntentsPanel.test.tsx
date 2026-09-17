/**
 * IntentsPanel tests (#323) — the delegation queue made visible.
 *
 * Pins the panel contract at the component boundary: open intents render in
 * queue order with dismiss, the recently-resolved section is collapsed until
 * toggled and shows resolution text, and the create form enqueues a free-text
 * `user_request` — attaching the selected canvas node as the target when the
 * user keeps the offer ticked.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as intentsApi from "@/api/intents";
import type { Intent } from "@/api/intents";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { IntentsPanel } from "./IntentsPanel";

function makeIntent(over: Partial<Intent> = {}): Intent {
  return {
    id: "i1",
    kind: "user_request",
    origin_canvas_id: "plant",
    target: null,
    payload: { text: "extract the pump curves" },
    status: "pending",
    created_at: 100,
    ...over,
  };
}

function renderPanel(over: {
  open?: Intent[];
  resolved?: Intent[];
  error?: string | null;
} = {}) {
  return render(
    <IntentsPanel
      workspaceSlug="plant"
      open={over.open ?? []}
      resolved={over.resolved ?? []}
      error={over.error ?? null}
    />,
  );
}

beforeEach(() => {
  useUiStore.setState({ selectedNodeId: null });
  useCanvasStore.setState({ nodes: {} });
});

afterEach(() => {
  vi.restoreAllMocks();
  useUiStore.setState({ selectedNodeId: null });
  useCanvasStore.setState({ nodes: {} });
});

describe("IntentsPanel listing", () => {
  it("renders open intents with title, kind, and origin canvas", () => {
    renderPanel({
      open: [
        makeIntent(),
        makeIntent({
          id: "i2",
          kind: "drop_to_ingest",
          payload: { filename: "pump.pdf", slug: "pump", node_id: "n9" },
        }),
      ],
    });
    expect(screen.getByText("Intents (2 open)")).toBeTruthy();
    expect(screen.getByText("extract the pump curves")).toBeTruthy();
    expect(screen.getByText("Ingest pump.pdf")).toBeTruthy();
    // The drop row surfaces its target node ref.
    expect(screen.getByText(/node n9/)).toBeTruthy();
  });

  it("shows an empty hint at zero", () => {
    renderPanel();
    expect(screen.getByText(/no open intents/)).toBeTruthy();
  });

  it("keeps recently resolved collapsed until toggled, then shows resolution text", () => {
    renderPanel({
      resolved: [
        makeIntent({
          id: "r1",
          status: "resolved",
          resolved_at: 200,
          result: { note: "curves plotted on canvas" },
        }),
      ],
    });
    expect(screen.queryByText("curves plotted on canvas")).toBeNull();

    fireEvent.click(screen.getByTestId("intents-resolved-toggle"));
    expect(screen.getByText("curves plotted on canvas")).toBeTruthy();
    const row = screen.getByTestId("intent-row");
    expect(row.getAttribute("data-status")).toBe("resolved");
  });

  it("dismisses an open intent by resolving it with {dismissed: true}", async () => {
    const resolve = vi.spyOn(intentsApi.intents, "resolve").mockResolvedValue(
      makeIntent({ status: "resolved" }),
    );
    renderPanel({ open: [makeIntent()] });

    await act(async () => {
      fireEvent.click(screen.getByTestId("intent-dismiss"));
    });
    expect(resolve).toHaveBeenCalledWith("i1", { dismissed: true });
  });
});

describe("IntentsPanel create form", () => {
  it("queues a free-text user_request without a node when nothing is selected", async () => {
    const create = vi.spyOn(intentsApi.intents, "create").mockResolvedValue(makeIntent());
    renderPanel();

    fireEvent.change(screen.getByTestId("intent-text-input"), {
      target: { value: "  compare inlet pressures  " },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("intent-submit"));
    });

    expect(create).toHaveBeenCalledWith({
      text: "compare inlet pressures",
      workspaceSlug: "plant",
      nodeId: null,
    });
    // The input clears after a successful queue.
    expect((screen.getByTestId("intent-text-input") as HTMLTextAreaElement).value).toBe("");
  });

  it("offers the selected canvas node as the target and attaches it", async () => {
    useCanvasStore.setState({
      nodes: {
        n1: { id: "n1", node_type: "spec", label: "Pump specs", x: 0, y: 0 },
      },
    });
    useUiStore.setState({ selectedNodeId: "n1" });
    const create = vi.spyOn(intentsApi.intents, "create").mockResolvedValue(makeIntent());
    renderPanel();

    // The offer names the node and is ticked by default.
    expect(screen.getByText(/target: Pump specs/)).toBeTruthy();

    fireEvent.change(screen.getByTestId("intent-text-input"), {
      target: { value: "fill in the missing rows" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("intent-submit"));
    });
    expect(create).toHaveBeenCalledWith({
      text: "fill in the missing rows",
      workspaceSlug: "plant",
      nodeId: "n1",
    });
  });

  it("unticking the offer drops the node ref", async () => {
    useCanvasStore.setState({
      nodes: { n1: { id: "n1", node_type: "spec", label: "Pump specs", x: 0, y: 0 } },
    });
    useUiStore.setState({ selectedNodeId: "n1" });
    const create = vi.spyOn(intentsApi.intents, "create").mockResolvedValue(makeIntent());
    renderPanel();

    fireEvent.click(screen.getByTestId("intent-attach-node"));
    fireEvent.change(screen.getByTestId("intent-text-input"), {
      target: { value: "general question" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("intent-submit"));
    });
    expect(create).toHaveBeenCalledWith({
      text: "general question",
      workspaceSlug: "plant",
      nodeId: null,
    });
  });

  it("surfaces a create failure inline", async () => {
    vi.spyOn(intentsApi.intents, "create").mockRejectedValue(new Error("nope"));
    renderPanel();
    fireEvent.change(screen.getByTestId("intent-text-input"), {
      target: { value: "will fail" },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("intent-submit"));
    });
    expect(screen.getByTestId("intents-action-error").textContent).toContain("nope");
  });
});
