/**
 * DocumentPrimitive click-isolation (#184, #27).
 *
 * The Document node's page-nav arrows and the "Open viewer" button are
 * interactive controls living inside a ReactFlow node. ReactFlow binds the
 * node-level open-the-viewer action to the DOM `dblclick` event on the node
 * element. A control's `onClick` stopPropagation does NOT stop that separate
 * `dblclick`, so a fast double-tap on the page arrow used to bubble up and
 * open the PDF viewer (#184).
 *
 * These tests pin two contracts:
 *   1. Clicking a page arrow pages the document (page indicator changes) and
 *      does NOT bubble click OR dblclick to a parent node-level handler.
 *   2. The node BODY still bubbles a double-click to the node-level handler
 *      so #27's "double-click the node to open the viewer" keeps working.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import { useUiStore } from "@/stores/uiStore";

import { DocumentPrimitive } from "./DocumentPrimitive";

beforeEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
  // The node fetches an index, a gold-map (raw fetch) and per-page regions.
  vi.spyOn(documents, "index").mockResolvedValue({
    document: { page_count: 3 },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.spyOn(documents, "regions").mockResolvedValue([]);
  vi.spyOn(documents, "locate").mockResolvedValue([]);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => null }),
  );
});

afterEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
  vi.restoreAllMocks();
});

async function renderDoc(data: Record<string, unknown>) {
  // A parent wrapper stands in for ReactFlow's node element. We attach
  // click + dblclick listeners to it and assert which events reach it.
  const onParentClick = vi.fn();
  const onParentDblClick = vi.fn();
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <MemoryRouter initialEntries={["/c/vasa"]}>
        <Routes>
          <Route
            path="/c/:id"
            element={
              <ReactFlowProvider>
                <div
                  data-testid="node-shell"
                  onClick={onParentClick}
                  onDoubleClick={onParentDblClick}
                >
                  <DocumentPrimitive
                    {...({
                      id: "doc1",
                      data,
                      selected: false,
                      dragging: false,
                      isConnectable: false,
                      positionAbsoluteX: 0,
                      positionAbsoluteY: 0,
                      type: "document",
                      zIndex: 0,
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    } as any)}
                  />
                </div>
              </ReactFlowProvider>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
  });
  return { ...result, onParentClick, onParentDblClick };
}

const READY_DOC = {
  label: "Pump datasheet",
  slug: "pump",
  status: "ready",
  page_count: 3,
};

describe("DocumentPrimitive click isolation", () => {
  it("paging via the next arrow changes the page and never opens the viewer", async () => {
    await renderDoc(READY_DOC);
    expect(screen.getByText(/page 1 \/ 3/)).toBeTruthy();

    const next = screen.getByRole("button", { name: "›" });
    await act(async () => {
      fireEvent.click(next);
    });

    expect(screen.getByText(/page 2 \/ 3/)).toBeTruthy();
    // The node-level open-viewer action must not have fired.
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("a fast double-click on the page arrow does NOT bubble to the node-level dblclick", async () => {
    const { onParentClick, onParentDblClick } = await renderDoc(READY_DOC);
    const next = screen.getByRole("button", { name: "›" });

    await act(async () => {
      fireEvent.click(next);
      fireEvent.click(next);
      fireEvent.doubleClick(next);
    });

    // Neither the click nor the dblclick reached the node shell, so the
    // ReactFlow node-level open-viewer handler can never fire (#184).
    expect(onParentClick).not.toHaveBeenCalled();
    expect(onParentDblClick).not.toHaveBeenCalled();
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("the 'Open viewer' button opens the viewer but does not bubble", async () => {
    const { onParentDblClick } = await renderDoc(READY_DOC);
    const open = screen.getByRole("button", { name: /Open viewer at page/ });

    await act(async () => {
      fireEvent.click(open);
    });

    expect(useUiStore.getState().pdfViewer).toMatchObject({ slug: "pump" });
    // A double-click on the button still must not reach the node shell.
    await act(async () => {
      fireEvent.doubleClick(open);
    });
    expect(onParentDblClick).not.toHaveBeenCalled();
  });

  it("locates the value text when a hovered ref carries a query, scoped to the region bbox (#197)", async () => {
    await renderDoc({ ...READY_DOC, slug: "alfa-laval-lkh" });
    // A spec row broadcasts its hover with the cell value (`query`) and the
    // region bbox. The document node must locate that text inside the region
    // for the value-precise highlight.
    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({
        slug: "alfa-laval-lkh",
        page: 1,
        region_id: "r9",
        bbox: [50, 480, 550, 410],
        query: "600 kPa",
      });
    });
    expect(documents.locate).toHaveBeenCalledWith(
      "alfa-laval-lkh",
      1,
      "600 kPa",
      [50, 480, 550, 410],
    );
  });

  it("does not locate when the hovered ref carries no query (region-only highlight)", async () => {
    await renderDoc({ ...READY_DOC, slug: "alfa-laval-lkh" });
    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({
        slug: "alfa-laval-lkh",
        page: 1,
        region_id: "r9",
        bbox: [50, 480, 550, 410],
      });
    });
    expect(documents.locate).not.toHaveBeenCalled();
  });

  it("double-clicking the node BODY still bubbles to the node-level handler (#27)", async () => {
    const { onParentDblClick } = await renderDoc(READY_DOC);
    // The label text lives in the body, outside any interactive control.
    const body = screen.getByText("Pump datasheet");
    await act(async () => {
      fireEvent.doubleClick(body);
    });
    // The dblclick reaches the shell, where ReactFlow would open the viewer.
    expect(onParentDblClick).toHaveBeenCalled();
  });
});
