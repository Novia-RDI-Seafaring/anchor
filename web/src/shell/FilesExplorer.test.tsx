/**
 * FilesExplorer.test.tsx — the left files explorer (#220 part B).
 *
 * Covers:
 *   - lists ingested documents + CAD via documents.list() / cad.list()
 *   - clicking a document opens it in the shared viewer (openPdf, dock mode)
 *   - the open document is highlighted as active (driven by pdfViewer.slug)
 *   - drag payloads are byte-for-byte the ones CanvasGraph's drop handler
 *     expects: `application/x-anchor-node` for docs + CAD; the canvas-link
 *     mime for canvases
 *   - the Canvases tab lists workspaces (the Canvases list keeps a home)
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as cadApi from "@/api/cad";
import type { CadModel } from "@/api/cad";
import * as canvasesApi from "@/api/canvases";
import type { WorkspaceListEntry } from "@/api/canvases";
import * as docsApi from "@/api/documents";
import type { DocumentSummary } from "@/api/documents";
import { DEFAULT_EXPLORER_WIDTH, DEFAULT_SOURCE_DOCK_RATIO, useUiStore } from "@/stores/uiStore";

import { CANVAS_LINK_MIME } from "./CanvasesPanel";
import { FilesExplorer } from "./FilesExplorer";

function makeDoc(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    slug: "pump-leaflet",
    title: "Pump Leaflet",
    filename: "pump_leaflet.pdf",
    page_count: 12,
    has_gold: true,
    region_count: 42,
    ...overrides,
  };
}

function makeCad(overrides: Partial<CadModel> = {}): CadModel {
  return {
    slug: "impeller",
    filename: "impeller.step",
    kind: "part",
    title: "Impeller",
    parameters: [{ name: "diameter" } as CadModel["parameters"][number]],
    parts: [],
    geometry: { triangle_count: 5000 } as CadModel["geometry"],
    ...overrides,
  } as CadModel;
}

function makeWorkspace(overrides: Partial<WorkspaceListEntry> = {}): WorkspaceListEntry {
  return {
    slug: "plant",
    title: "Plant",
    node_count: 3,
    edge_count: 2,
    references: [],
    ...overrides,
  } as WorkspaceListEntry;
}

function resetUi() {
  useUiStore.setState({
    pdfViewer: null,
    sourceDockRatio: DEFAULT_SOURCE_DOCK_RATIO,
    explorerWidth: DEFAULT_EXPLORER_WIDTH,
    sourceClusterCollapsed: false,
  });
}

beforeEach(() => {
  resetUi();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// A minimal DataTransfer stub so onDragStart can record payloads in jsdom.
function makeDataTransfer() {
  const store: Record<string, string> = {};
  return {
    effectAllowed: "",
    setData: (type: string, val: string) => {
      store[type] = val;
    },
    getData: (type: string) => store[type] ?? "",
    _store: store,
  } as unknown as DataTransfer & { _store: Record<string, string> };
}

describe("FilesExplorer listing", () => {
  it("lists ingested documents and CAD models", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([makeDoc()]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([makeCad()]);
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([]);

    render(<FilesExplorer workspaceSlug="plant" />);

    await waitFor(() => {
      expect(screen.getByText("Pump Leaflet")).toBeTruthy();
    });
    expect(screen.getByText("Impeller")).toBeTruthy();
  });
});

describe("FilesExplorer click-to-open + active highlight", () => {
  it("clicking a document opens it in the viewer (dock mode, wired to canvas)", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([makeDoc({ slug: "doc-a" })]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([]);
    const openPdf = vi.spyOn(useUiStore.getState(), "openPdf");

    render(<FilesExplorer workspaceSlug="plant" />);

    const row = await screen.findByTestId("document-item");
    act(() => {
      fireEvent.click(row);
    });

    expect(openPdf).toHaveBeenCalledWith("doc-a", {
      mode: "dock",
      workspaceSlug: "plant",
    });
  });

  it("highlights the open document as active", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([
      makeDoc({ slug: "doc-a", title: "Doc A" }),
      makeDoc({ slug: "doc-b", title: "Doc B" }),
    ]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([]);
    // doc-b is the open document.
    act(() => {
      useUiStore.setState({
        pdfViewer: { slug: "doc-b", page: 1, mode: "dock" },
      });
    });

    const { container } = render(<FilesExplorer workspaceSlug="plant" />);

    await waitFor(() => {
      expect(screen.getByText("Doc B")).toBeTruthy();
    });

    const active = container.querySelector('[data-slug="doc-b"]');
    const inactive = container.querySelector('[data-slug="doc-a"]');
    expect((active as HTMLElement).getAttribute("data-active")).toBe("true");
    expect((inactive as HTMLElement).getAttribute("data-active")).toBe("false");
  });
});

describe("FilesExplorer drag payloads", () => {
  it("a document drag carries the application/x-anchor-node document payload", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([makeDoc({ slug: "doc-a" })]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([]);

    render(<FilesExplorer workspaceSlug="plant" />);

    const row = await screen.findByTestId("document-item");
    const dt = makeDataTransfer();
    fireEvent.dragStart(row, { dataTransfer: dt });

    const raw = dt.getData("application/x-anchor-node");
    expect(raw).not.toBe("");
    const payload = JSON.parse(raw);
    expect(payload.node_type).toBe("document");
    expect(payload.data.slug).toBe("doc-a");
  });

  it("a CAD drag carries the application/x-anchor-node cad:model payload", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([makeCad({ slug: "imp-1" })]);
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([]);

    render(<FilesExplorer workspaceSlug="plant" />);

    await waitFor(() => {
      expect(screen.getByText("Impeller")).toBeTruthy();
    });
    const cadRow = screen.getByText("Impeller").closest("[draggable]") as HTMLElement;
    const dt = makeDataTransfer();
    fireEvent.dragStart(cadRow, { dataTransfer: dt });

    const payload = JSON.parse(dt.getData("application/x-anchor-node"));
    expect(payload.node_type).toBe("cad:model");
    expect(payload.data.cad_slug).toBe("imp-1");
  });

  it("a canvas drag carries the canvas-link mime payload", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([
      makeWorkspace({ slug: "loop", title: "Loop" }),
    ]);

    render(<FilesExplorer workspaceSlug="plant" />);

    // Switch to the Canvases tab.
    fireEvent.click(screen.getByRole("tab", { name: "Canvases" }));

    const linkRow = await screen.findByTestId("canvas-link-item");
    const dt = makeDataTransfer();
    fireEvent.dragStart(linkRow, { dataTransfer: dt });

    const payload = JSON.parse(dt.getData(CANVAS_LINK_MIME));
    expect(payload.slug).toBe("loop");
    expect(payload.title).toBe("Loop");
  });
});
