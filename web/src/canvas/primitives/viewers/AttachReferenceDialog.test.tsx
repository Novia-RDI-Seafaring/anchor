import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { references } from "@/api/references";
import { useCanvasStore, type Reference } from "@/stores/canvasStore";
import { AttachReferenceDialog } from "./AttachReferenceDialog";

const reference: Reference = { id: "ref-1", source_ref: { slug: "norrhavn-px", page: 1 }, created_by: "human", created_at: 1 };
const onClose = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  useCanvasStore.getState().reset();
  useCanvasStore.setState({ slug: "board", references: [reference], nodes: { n1: { id: "n1", node_type: "fact", label: "Pump", x: 0, y: 0, data: { text: "Rated at 10 bar.", keep: "unchanged", rows: [{ key: "Pressure", value: "10 bar" }] } } } });
});
afterEach(() => vi.restoreAllMocks());
function draw() { render(<AttachReferenceDialog canvasSlug="board" nodeId="n1" reference={reference} onClose={onClose} />); }
function selectWords() {
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "text" } });
  const text = screen.getByRole("textbox") as HTMLTextAreaElement;
  text.setSelectionRange(9, 15);
  fireEvent.select(text);
}

describe("AttachReferenceDialog", () => {
  it.each([["node", { node_id: "n1" }], ["row:0", { node_id: "n1", row_index: 0 }]])("attaches to %s through the existing operation", async (target, expected) => {
    const attach = vi.spyOn(references, "attach").mockResolvedValue({ event: { id: "e", type: "ReferenceAttached", workspace_id: "board", version: 1, payload: {}, ts: 0 } });
    draw();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: target } });
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    await waitFor(() => expect(attach).toHaveBeenCalledWith("board", "ref-1", expected));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("wraps selected words in a reusable ID citation with a partial text patch", async () => {
    const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({});
    draw(); selectWords();
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("board", "n1", { data: { text: "Rated at [10 bar](anchor:ref/ref-1)." } }));
  });

  it("preserves remote edits while the dialog is open", async () => {
    const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({});
    draw(); selectWords();
    act(() => useCanvasStore.setState((state) => ({ nodes: { n1: { ...state.nodes.n1!, data: { text: "Changed by agent" } } } })));
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The text changed. Cancel and select the words again.");
    expect(patch).not.toHaveBeenCalled();
  });

  it("keeps a failed attachment open for retry", async () => {
    vi.spyOn(references, "attach").mockRejectedValue(new Error("Server unavailable"));
    draw();
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Server unavailable");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not attach to a different row after a remote reorder", async () => {
    const attach = vi.spyOn(references, "attach").mockResolvedValue({});
    draw();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "row:0" } });
    act(() => useCanvasStore.setState((state) => ({ nodes: { n1: { ...state.nodes.n1!, data: { rows: [{ key: "Temperature", value: "140 C" }, { key: "Pressure", value: "10 bar" }] } } } })));
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The row changed. Cancel and select the row again.");
    expect(attach).not.toHaveBeenCalled();
  });

  it("does not insert a reference deleted while selecting words", async () => {
    const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({});
    draw(); selectWords();
    act(() => useCanvasStore.setState({ references: [] }));
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The reference was deleted. Choose an existing reference.");
    expect(patch).not.toHaveBeenCalled();
  });

  it("does not allow writes to a locked target", () => {
    useCanvasStore.setState((state) => ({ nodes: { n1: { ...state.nodes.n1!, locked: true } } }));
    draw();
    expect((screen.getByRole("button", { name: "Attach" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

