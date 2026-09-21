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
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import geometryFixture from "@/lib/fixtures/documentPageGeometry.json";
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
  vi.useRealTimers();
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
  it.each(["72", "150", "300"] as const)("maps the actual backend page_size payload at %s DPI", async (dpi) => {
    vi.mocked(documents.regions).mockResolvedValue(geometryFixture.gold_map.pages["1"]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => geometryFixture.gold_map }));
    const { container } = await renderDoc(READY_DOC);
    const image = screen.getByRole("img") as HTMLImageElement;
    Object.defineProperties(image, {
      naturalWidth: { value: geometryFixture.rasters[dpi]["1"].width },
      naturalHeight: { value: geometryFixture.rasters[dpi]["1"].height },
    });
    await act(async () => { fireEvent.load(image); });
    const overlay = container.querySelector<HTMLElement>('[data-region-handle-id="region:review"]');
    expect(overlay).not.toBeNull();
    expect(parseFloat(overlay!.style.left)).toBeCloseTo(10);
    expect(parseFloat(overlay!.style.top)).toBeCloseTo(12.5);
    expect(parseFloat(overlay!.style.width)).toBeCloseTo(30);
    expect(parseFloat(overlay!.style.height)).toBeCloseTo(6.25);
    for (const [id, bbox] of Object.entries(geometryFixture.boxes["1"])) {
      const box = container.querySelector<HTMLElement>(`[data-region-handle-id="region:${id}"]`)!;
      expect(parseFloat(box.style.left)).toBeCloseTo(bbox[0]! / 600 * 100, 10);
      expect(parseFloat(box.style.top)).toBeCloseTo(bbox[1]! / 800 * 100, 10);
      expect(parseFloat(box.style.width)).toBeCloseTo((bbox[2]! - bbox[0]!) / 600 * 100, 10);
      expect(parseFloat(box.style.height)).toBeCloseTo((bbox[3]! - bbox[1]!) / 800 * 100, 10);
    }
  });

  it("uses each unequal page's geometry, including unrotated landscape", async () => {
    vi.mocked(documents.regions).mockImplementation(async (_, page) =>
      geometryFixture.gold_map.pages[String(page) as "1" | "2" | "3"]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => geometryFixture.gold_map }));
    const { container } = await renderDoc(READY_DOC);
    for (const page of ["1", "2", "3"] as const) {
      if (page !== "1") await act(async () => { fireEvent.click(screen.getByRole("button", { name: "\u203a" })); });
      const image = screen.getByRole("img") as HTMLImageElement;
      Object.defineProperties(image, {
        naturalWidth: { value: geometryFixture.rasters["300"][page].width },
        naturalHeight: { value: geometryFixture.rasters["300"][page].height },
      });
      await act(async () => { fireEvent.load(image); });
      const [width, height] = geometryFixture.gold_map.pages_meta.pages[page].page_size;
      const overlay = container.querySelector<HTMLElement>('[data-region-handle-id="region:review"]')!;
      expect(parseFloat(overlay.style.left)).toBeCloseTo(60 / width! * 100, 10);
      expect(parseFloat(overlay.style.top)).toBeCloseTo(100 / height! * 100, 10);
      expect(parseFloat(overlay.style.width)).toBeCloseTo(180 / width! * 100, 10);
      expect(parseFloat(overlay.style.height)).toBeCloseTo(50 / height! * 100, 10);
    }
  });

  it.each([null, { pages: { "1": { page_size: [0, 800] } } }])(
    "keeps the image but omits precise overlays when dimensions are unknown: %j", async (pages_meta) => {
      vi.mocked(documents.regions).mockResolvedValue(geometryFixture.gold_map.pages["1"]);
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ pages_meta }) }));
      const { container } = await renderDoc(READY_DOC);
      const image = screen.getByRole("img") as HTMLImageElement;
      Object.defineProperties(image, { naturalWidth: { value: 600 }, naturalHeight: { value: 800 } });
      await act(async () => { fireEvent.load(image); });
      expect(container.querySelector("[data-region-handle-id]")).toBeNull();
      expect(screen.getByRole("status").textContent).toContain("page dimensions unknown");
      expect(image.style.display).toBe("block");
    },
  );

  it("uses the same page scale for caller bboxes and precise located value quads", async () => {
    const bbox = [72, 108, 96, 120];
    vi.mocked(documents.regions).mockResolvedValue(geometryFixture.gold_map.pages["1"]);
    vi.mocked(documents.locate).mockResolvedValue([bbox]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => geometryFixture.gold_map }));
    await renderDoc(READY_DOC);
    const image = screen.getByRole("img") as HTMLImageElement;
    Object.defineProperties(image, { naturalWidth: { value: 600 }, naturalHeight: { value: 800 } });
    await act(async () => {
      fireEvent.load(image);
      useUiStore.getState().setHoveredSourceRef({ slug: "pump", page: 1, bbox, region_id: "review", query: "value" });
    });
    const quad = screen.getByTestId("value-quad");
    expect(quad.style.left).toBe("12%");
    expect(parseFloat(quad.style.top)).toBeCloseTo(13.5);
    expect(quad.style.width).toBe("4%");
    expect(parseFloat(quad.style.height)).toBeCloseTo(1.5);
    // Found by name now rather than by its colour: the caller highlight and
    // the value quad are the same mark as the source pane draws, so neither
    // carries a background of its own to match on.
    const caller = screen.getByTestId("external-highlight");
    expect(caller.style.left).toBe(quad.style.left);
    expect(caller.style.top).toBe(quad.style.top);
    expect(caller.className).toContain("anchor-mark");
    expect(quad.className).toContain("anchor-mark");
    expect(useUiStore.getState().hoveredSourceRef?.bbox).toEqual(bbox);
  });

  it("drops the removed LKH page and region when replacement publishes", async () => {
    vi.useFakeTimers();
    vi.mocked(documents.regions).mockResolvedValue([{ id: "removed", title: "Water pressure inlet", bbox: [10, 10, 30, 30] }]);
    await renderDoc(READY_DOC);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "›" })); });
    expect(screen.getByText(/page 2 \/ 3/)).toBeTruthy();
    vi.mocked(documents.regions).mockResolvedValue([]);
    vi.mocked(documents.index).mockResolvedValue({ document: { page_count: 1, title: "Alfa Laval LKH", filename: "Alfa Laval LKH.pdf",
      generation: { id: "replacement-b", pages: [1] } }, outline: [] } as Awaited<ReturnType<typeof documents.index>>);
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(screen.getByText("1 page")).toBeTruthy();
    expect(screen.queryByText("Water pressure inlet")).toBeNull();
    expect(screen.getByRole("button", { name: "Open viewer at page 1" })).toBeTruthy();
  });

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

/**
 * Transient hover-driven page flip (#187).
 *
 * Hovering a node that cites a page broadcasts a `hoveredSourceRef`, which
 * flips the document preview to that page. On hover-out the ref clears, and
 * the preview must revert to its resting page (the cover) instead of sticking
 * on the last referenced page. Deliberate page navigation (arrows) and a
 * pinned/sticky reference (a selected referencing node) survive that revert.
 */
describe("DocumentPrimitive selector precision", () => {
  it("resolves a cell ref so the preview boxes the cell, not the whole section", async () => {
    // The dock already lands on the cell; hover used to drop the selector, so
    // this preview drew a box around the whole Temperature section while the
    // dock highlighted one value. The two surfaces must agree.
    const resolveRef = vi
      .spyOn(documents, "resolveRef")
      .mockResolvedValue({ page: 2, bbox: [10, 20, 30, 40], precision: "cell" } as never);
    await renderDoc(READY_DOC);

    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({
        slug: "pump",
        page: 2,
        region_id: "r9",
        bbox: [0, 0, 500, 200],
        cell: { row: 1, col: 1 },
      });
    });

    await waitFor(() => expect(resolveRef).toHaveBeenCalled());
    const [slugArg, refArg] = resolveRef.mock.calls[0]!;
    expect(slugArg).toBe("pump");
    expect((refArg as { cell?: unknown }).cell).toEqual({ row: 1, col: 1 });
  });

  it("does not resolve a ref that carries no selector", async () => {
    const resolveRef = vi.spyOn(documents, "resolveRef").mockResolvedValue(null as never);
    await renderDoc(READY_DOC);

    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({
        slug: "pump", page: 2, region_id: "r9", bbox: [0, 0, 500, 200],
      });
    });

    expect(resolveRef).not.toHaveBeenCalled();
  });

  it("falls back to the region when resolving fails, so it never shows nothing", async () => {
    vi.spyOn(documents, "resolveRef").mockRejectedValue(new Error("boom"));
    await renderDoc(READY_DOC);

    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({
        slug: "pump", page: 2, region_id: "r9", bbox: [0, 0, 500, 200], cell: { row: 1, col: 1 },
      });
    });

    // Still flipped to the page and still rendering; the region-level
    // highlight remains the graceful fallback.
    expect(screen.getByText(/page 2 \/ 3/)).toBeTruthy();
  });
});

describe("DocumentPrimitive hover-driven page revert (#187)", () => {
  it("hovering a node citing page N flips the preview to N", async () => {
    await renderDoc(READY_DOC);
    expect(screen.getByText(/page 1 \/ 3/)).toBeTruthy();

    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({ slug: "pump", page: 3 });
    });

    expect(screen.getByText(/page 3 \/ 3/)).toBeTruthy();
  });

  it("hover-out reverts the preview to the cover (page 1)", async () => {
    await renderDoc(READY_DOC);

    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({ slug: "pump", page: 3 });
    });
    expect(screen.getByText(/page 3 \/ 3/)).toBeTruthy();

    await act(async () => {
      useUiStore.getState().clearHoveredSourceRef();
    });
    // No ref pointing here anymore — back to the cover without clicking
    // through every page.
    expect(screen.getByText(/page 1 \/ 3/)).toBeTruthy();
  });

  it("a ref pointing at a different document does not strand this preview", async () => {
    await renderDoc(READY_DOC);

    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({ slug: "pump", page: 2 });
    });
    expect(screen.getByText(/page 2 \/ 3/)).toBeTruthy();

    // Hovering a reference into some OTHER document is, for this node, the
    // same as no reference: it settles back on the cover.
    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({ slug: "other", page: 5 });
    });
    expect(screen.getByText(/page 1 \/ 3/)).toBeTruthy();
  });

  it("explicit arrow navigation is not auto-reverted on hover-out", async () => {
    await renderDoc(READY_DOC);

    // Deliberately page to 2 via the arrow.
    const next = screen.getByRole("button", { name: "›" });
    await act(async () => {
      fireEvent.click(next);
    });
    expect(screen.getByText(/page 2 \/ 3/)).toBeTruthy();

    // A transient hover flips to 3, then clears.
    await act(async () => {
      useUiStore.getState().setHoveredSourceRef({ slug: "pump", page: 3 });
    });
    expect(screen.getByText(/page 3 \/ 3/)).toBeTruthy();

    await act(async () => {
      useUiStore.getState().clearHoveredSourceRef();
    });
    // Reverts to the manually-set resting page (2), not the cover.
    expect(screen.getByText(/page 2 \/ 3/)).toBeTruthy();
  });

  it("a sticky (pinned) reference keeps the preview on its page after clear", async () => {
    await renderDoc(READY_DOC);

    // A selected referencing node broadcasts a sticky ref.
    await act(async () => {
      useUiStore
        .getState()
        .setHoveredSourceRef({ slug: "pump", page: 3, sticky: true });
    });
    expect(screen.getByText(/page 3 \/ 3/)).toBeTruthy();

    // Clearing the hover must NOT fight the deliberate selection.
    await act(async () => {
      useUiStore.getState().clearHoveredSourceRef();
    });
    expect(screen.getByText(/page 3 \/ 3/)).toBeTruthy();
  });
});
