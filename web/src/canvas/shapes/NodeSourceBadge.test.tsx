import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import type { ComponentType } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import { OPEN_DELAY_MS } from "@/canvas/RefHoverPreview";
import { useUiStore } from "@/stores/uiStore";

import { ConceptNode } from "./ConceptNode";
import { EntityNode } from "./EntityNode";
import { FactNode } from "./FactNode";
import { NoteNode } from "./NoteNode";

const source = { slug: "pump-datasheet", page: 3, region_id: "r2", bbox: [10, 20, 80, 40] };

function draw(Node: ComponentType<NodeProps>, sourceRef: unknown = source, onCanvasClick = vi.fn()) {
  return render(
    <MemoryRouter initialEntries={["/canvas/pump-selection"]}>
      <Routes>
        <Route path="/canvas/:id" element={
          <ReactFlowProvider>
            <div onClick={onCanvasClick}>
              <Node
                id="grounded-node"
                type="fact"
                data={{ label: "Operating limit", text: "120 C", source_ref: sourceRef }}
                selected={false}
                dragging={false}
                draggable
                selectable
                deletable
                isConnectable={false}
                positionAbsoluteX={0}
                positionAbsoluteY={0}
                zIndex={0}
              />
            </div>
          </ReactFlowProvider>
        } />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useUiStore.setState({ pdfViewer: null, pdfViewerPinned: false, hoveredSourceRef: null, hoverPreviewMode: "viewer" });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe.each([
  ["fact", FactNode],
  ["note", NoteNode],
  ["concept", ConceptNode],
  ["entity", EntityNode],
] as const)("%s node provenance", (_name, Node) => {
  it("shows the document and page, exposes the region, and opens its source without a document node", () => {
    const onCanvasClick = vi.fn();
    draw(Node, source, onCanvasClick);
    const button = screen.getByRole("button", { name: /Open source: pump-datasheet.*page 3.*region r2/ });
    expect(button.textContent).toContain("pump-datasheet");
    expect(button.textContent).toContain("p. 3");
    expect(button.title).toContain("region r2");
    fireEvent.click(button);
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: source.slug,
      page: source.page,
      workspaceSlug: "pump-selection",
      highlightRegionId: source.region_id,
      highlightBbox: source.bbox,
    });
    expect(useUiStore.getState().pdfViewerPinned).toBe(true);
    expect(onCanvasClick).not.toHaveBeenCalled();
  });

  it("leaves a node without provenance unchanged", () => {
    draw(Node, null);
    expect(screen.queryByRole("button", { name: /Open source:/ })).toBeNull();
    expect(screen.getByText("Operating limit")).toBeTruthy();
  });
});

it.each([{}, { slug: "pump" }, { page: 3 }, { slug: "", page: 3 }, { slug: "pump", page: 0 }, { slug: "pump", page: 1.5 }])(
  "does not offer a dead viewer action for an incomplete reference: %j", (ref) => {
    draw(FactNode, ref);
    expect(screen.queryByRole("button", { name: /Open source:/ })).toBeNull();
  },
);

it("resolves below-region selectors before opening the source", async () => {
  const ref = { ...source, item_id: "p3-i1", cell: { row: 2, col: 1 } };
  const resolvedBox = [20, 25, 60, 35];
  const resolve = vi.spyOn(documents, "resolveRef").mockResolvedValue({ slug: source.slug, page: 3, bbox: resolvedBox, precision: "cell" });
  draw(FactNode, ref);
  fireEvent.click(screen.getByRole("button", { name: /Open source:/ }));
  await waitFor(() => expect(useUiStore.getState().pdfViewer?.highlightBbox).toEqual(resolvedBox));
  expect(resolve).toHaveBeenCalledWith(source.slug, ref);
});

it("opens a transient hover preview and pins it on click", () => {
  vi.useFakeTimers();
  draw(FactNode);
  const button = screen.getByRole("button", { name: /Open source:/ });
  fireEvent.mouseEnter(button);
  fireEvent.mouseMove(button);
  expect(useUiStore.getState().hoveredSourceRef).toMatchObject(source);
  expect(useUiStore.getState().pdfViewer).toBeNull();
  act(() => vi.advanceTimersByTime(OPEN_DELAY_MS + 1));
  expect(useUiStore.getState().pdfViewer).toMatchObject({ slug: source.slug, highlightBbox: source.bbox });
  expect(useUiStore.getState().pdfViewerPinned).toBe(false);
  fireEvent.click(button);
  expect(useUiStore.getState().pdfViewerPinned).toBe(true);
  fireEvent.mouseLeave(button);
  expect(useUiStore.getState().hoveredSourceRef).toBeNull();
});
