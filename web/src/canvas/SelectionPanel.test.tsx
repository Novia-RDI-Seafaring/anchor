/**
 * SelectionPanel — the properties of whatever is selected, open on the left.
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canvases } from "@/api/canvases";

import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { SelectionPanel } from "./SelectionPanel";

function seed(nodes: Record<string, unknown>) {
  useCanvasStore.setState({ nodes: nodes as never });
}

function renderPanel() {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route path="/canvas/:id" element={<SelectionPanel />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SelectionPanel", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    useUiStore.setState({ selectedNodeId: null });
    seed({});
  });

  it("stays out of the way when nothing is selected", () => {
    const { queryByTestId } = renderPanel();
    expect(queryByTestId("selection-panel")).toBeNull();
  });

  it("shows fill, stroke and text for a shape", () => {
    seed({ n1: { id: "n1", node_type: "concept", data: { label: "A" } } });
    useUiStore.setState({ selectedNodeId: "n1" });
    const { getByTestId } = renderPanel();
    const text = getByTestId("selection-panel").textContent ?? "";
    expect(text).toContain("Fill");
    expect(text).toContain("Stroke");
    expect(text).toContain("Text");
  });

  it("shows only text for a text element, which has no box to colour", () => {
    seed({ t1: { id: "t1", node_type: "text", data: { text: "hello" } } });
    useUiStore.setState({ selectedNodeId: "t1" });
    const { getByTestId } = renderPanel();
    const text = getByTestId("selection-panel").textContent ?? "";
    expect(text).toContain("Text");
    expect(text).not.toContain("Fill");
    expect(text).not.toContain("Stroke");
  });

  it("sets a heading through the existing data patch and hides irrelevant box styling", async () => {
    const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({});
    seed({ n1: { id: "n1", node_type: "concept", data: { source_ref: { slug: "manual", page: 2 } } } });
    useUiStore.setState({ selectedNodeId: "n1" });
    const { getByLabelText, rerender, getByTestId } = renderPanel();
    fireEvent.change(getByLabelText("Node appearance"), { target: { value: "heading" } });
    await waitFor(() => expect(patch).toHaveBeenCalledWith("w1", "n1", { data: { role: "heading" } }));
    seed({ n1: { id: "n1", node_type: "concept", data: { role: "heading" } } });
    rerender(<MemoryRouter initialEntries={["/canvas/w1"]}><Routes><Route path="/canvas/:id" element={<SelectionPanel />} /></Routes></MemoryRouter>);
    expect(getByTestId("selection-panel").textContent).not.toContain("Fill");
    patch.mockRestore();
  });

  it("resets a saved larger size to Medium through the JSON update and survives reload", async () => {
    const original = {
      text: "Pump operating limits",
      text_bold: true,
      text_align: "right",
      text_family: "serif",
      source_ref: { slug: "pump", page: 2, bbox: [10, 20, 30, 40] },
    };
    let saved: Record<string, unknown> = { ...original };
    let version = 0;
    const fetchPatch = vi.fn(async (_url: unknown, options: RequestInit) => {
      // Use the real API client's JSON body. Omitted keys preserve saved
      // values, as the existing partial-data update contract requires.
      const body = JSON.parse(options.body as string) as { data: Record<string, unknown> };
      saved = { ...saved, ...body.data };
      version += 1;
      useCanvasStore.getState().applyEvent({
        id: `size-${version}`, type: "NodeUpdated", workspace_id: "w1",
        version, ts: 0, payload: { id: "t1", fields: { data: saved } },
      });
      return new Response(JSON.stringify({ data: saved }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchPatch);
    seed({ t1: { id: "t1", node_type: "text", data: original } });
    useCanvasStore.setState({ version: 0 });
    useUiStore.setState({ selectedNodeId: "t1" });
    const panel = renderPanel();

    fireEvent.click(panel.getByLabelText("text size 3 extra large"));
    await waitFor(() => expect(saved.text_size).toBe("3xl"));
    expect(panel.getByLabelText("text size 3 extra large").getAttribute("aria-checked")).toBe("true");
    fireEvent.click(panel.getByLabelText("text size medium"));
    await waitFor(() => expect(panel.getByLabelText("text size medium").getAttribute("aria-checked")).toBe("true"));
    expect(saved).toEqual({ ...original, text_size: "md" });
    expect(fetchPatch).toHaveBeenCalledTimes(2);

    panel.unmount();
    seed({ t1: { id: "t1", node_type: "text", data: JSON.parse(JSON.stringify(saved)) } });
    const reloaded = renderPanel();
    expect(reloaded.getByLabelText("text size medium").getAttribute("aria-checked")).toBe("true");
    expect(reloaded.getByLabelText("text size 3 extra large").getAttribute("aria-checked")).toBe("false");
  });
});
