/**
 * uiStore unit tests — pinning the armed-tool state transitions and the
 * mutual exclusion between the Library drawer and the Properties panel.
 *
 * Why this test exists: the left tool rail relies on `armedTool` being a
 * predictable single source of truth. A bug where clicking the same icon
 * twice fails to disarm, or where arming a tool leaves a stale value
 * around, would make the canvas un-clickable. Pin both gestures.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_EXPLORER_WIDTH,
  DEFAULT_SOURCE_DOCK_RATIO,
  useUiStore,
} from "./uiStore";

/**
 * Install an in-memory localStorage stub. This jsdom build does not provide a
 * working Storage (its methods are missing), and the store guards against that
 * by falling back to in-memory. To assert the *persistence* behaviour we swap
 * in a real stub for the duration of a test.
 */
function installLocalStorageStub(): Record<string, string> {
  const store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  });
  return store;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  // Reset to the initial state by setting every field individually — the
  // store has no `reset()` action.
  useUiStore.setState({
    pdfViewer: null,
    sourceDockRatio: DEFAULT_SOURCE_DOCK_RATIO,
    explorerWidth: DEFAULT_EXPLORER_WIDTH,
    sourceClusterCollapsed: false,
    hoveredSourceRef: null,
    armedTool: null,
    selectedNodeId: null,
    selectedEdgeId: null,
    propertiesOpen: false,
    dropTargetAreaId: null,
    isDraggingNode: false,
    pendingInlineRenameNodeId: null,
  });
});

describe("uiStore.armTool", () => {
  it("arms a tool when none is set", () => {
    useUiStore.getState().armTool("concept");
    expect(useUiStore.getState().armedTool).toBe("concept");
  });

  it("toggles the tool off when armed with the same type twice", () => {
    const { armTool } = useUiStore.getState();
    armTool("concept");
    armTool("concept");
    expect(useUiStore.getState().armedTool).toBeNull();
  });

  it("replaces the armed tool when a different type is armed", () => {
    const { armTool } = useUiStore.getState();
    armTool("concept");
    armTool("entity");
    expect(useUiStore.getState().armedTool).toBe("entity");
  });

  it("disarmTool clears the armed tool", () => {
    useUiStore.setState({ armedTool: "funnel" });
    useUiStore.getState().disarmTool();
    expect(useUiStore.getState().armedTool).toBeNull();
  });

  it("disarmTool is a no-op when nothing is armed", () => {
    useUiStore.getState().disarmTool();
    expect(useUiStore.getState().armedTool).toBeNull();
  });
});

describe("uiStore.dropTargetAreaId", () => {
  it("defaults to null", () => {
    expect(useUiStore.getState().dropTargetAreaId).toBeNull();
  });

  it("setDropTargetAreaId stores the id", () => {
    useUiStore.getState().setDropTargetAreaId("area-1");
    expect(useUiStore.getState().dropTargetAreaId).toBe("area-1");
  });

  it("setDropTargetAreaId(null) clears the target", () => {
    useUiStore.setState({ dropTargetAreaId: "area-1" });
    useUiStore.getState().setDropTargetAreaId(null);
    expect(useUiStore.getState().dropTargetAreaId).toBeNull();
  });
});

describe("uiStore.isDraggingNode", () => {
  it("defaults to false", () => {
    expect(useUiStore.getState().isDraggingNode).toBe(false);
  });

  it("setIsDraggingNode toggles the flag", () => {
    useUiStore.getState().setIsDraggingNode(true);
    expect(useUiStore.getState().isDraggingNode).toBe(true);
    useUiStore.getState().setIsDraggingNode(false);
    expect(useUiStore.getState().isDraggingNode).toBe(false);
  });
});

describe("uiStore.pendingInlineRenameNodeId", () => {
  it("defaults to null", () => {
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
  });

  it("requestInlineRename stores the id", () => {
    useUiStore.getState().requestInlineRename("node-7");
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBe("node-7");
  });

  it("consumeInlineRename returns true and clears when ids match", () => {
    useUiStore.getState().requestInlineRename("node-7");
    const ok = useUiStore.getState().consumeInlineRename("node-7");
    expect(ok).toBe(true);
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
  });

  it("consumeInlineRename returns false and does not clear when ids differ", () => {
    useUiStore.getState().requestInlineRename("node-7");
    const ok = useUiStore.getState().consumeInlineRename("node-8");
    expect(ok).toBe(false);
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBe("node-7");
  });

  it("consumeInlineRename returns false when nothing is pending", () => {
    const ok = useUiStore.getState().consumeInlineRename("node-7");
    expect(ok).toBe(false);
  });
});

describe("uiStore PDF source highlights", () => {
  it("records the page that owns a source-ref bbox highlight", () => {
    useUiStore.getState().openPdf("lkh", {
      page: 2,
      highlightBbox: [10, 20, 30, 40],
    });

    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "lkh",
      page: 2,
      highlightBbox: [10, 20, 30, 40],
      highlightPage: 2,
    });
  });

  it("keeps the source highlight tied to its original page while browsing", () => {
    useUiStore.getState().openPdf("lkh", {
      page: 2,
      highlightRegionId: "r4",
      highlightBbox: [10, 20, 30, 40],
    });

    useUiStore.getState().setPdfPage(3);

    expect(useUiStore.getState().pdfViewer).toMatchObject({
      page: 3,
      highlightRegionId: "r4",
      highlightBbox: [10, 20, 30, 40],
      highlightPage: 2,
    });
  });
});

describe("uiStore.selectedEdgeId — Miro-style edge editor selection", () => {
  it("defaults to null", () => {
    expect(useUiStore.getState().selectedEdgeId).toBeNull();
  });

  it("setSelectedEdgeId stores the id", () => {
    useUiStore.getState().setSelectedEdgeId("e1");
    expect(useUiStore.getState().selectedEdgeId).toBe("e1");
  });

  it("selecting an edge clears any selected node (mutual exclusion)", () => {
    useUiStore.setState({ selectedNodeId: "n1" });
    useUiStore.getState().setSelectedEdgeId("e1");
    const s = useUiStore.getState();
    expect(s.selectedEdgeId).toBe("e1");
    expect(s.selectedNodeId).toBeNull();
  });

  it("selecting a node clears any selected edge", () => {
    useUiStore.setState({ selectedEdgeId: "e1" });
    useUiStore.getState().setSelectedNodeId("n1");
    const s = useUiStore.getState();
    expect(s.selectedNodeId).toBe("n1");
    expect(s.selectedEdgeId).toBeNull();
  });

  it("setSelectedNodeId(null) does not clobber the edge selection", () => {
    useUiStore.setState({ selectedEdgeId: "e1", selectedNodeId: null });
    useUiStore.getState().setSelectedNodeId(null);
    expect(useUiStore.getState().selectedEdgeId).toBe("e1");
  });

  it("setSelectedEdgeId(null) does not clobber the node selection", () => {
    useUiStore.setState({ selectedEdgeId: null, selectedNodeId: "n1" });
    useUiStore.getState().setSelectedEdgeId(null);
    expect(useUiStore.getState().selectedNodeId).toBe("n1");
  });
});

describe("uiStore split-screen source dock (#110a)", () => {
  it("openPdf defaults to the docked split-screen mode", () => {
    useUiStore.getState().openPdf("lkh", { page: 1 });
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "lkh",
      page: 1,
      mode: "dock",
    });
  });

  it("openPdf can pin the modal quick-look mode", () => {
    useUiStore.getState().openPdf("lkh", { page: 1, mode: "modal" });
    expect(useUiStore.getState().pdfViewer?.mode).toBe("modal");
  });

  it("opening a second document reuses the pane and keeps the current mode", () => {
    // Open in modal, then open a different document with no mode given.
    useUiStore.getState().openPdf("doc-a", { page: 3, mode: "modal" });
    useUiStore.getState().openPdf("doc-b", { page: 1 });
    const v = useUiStore.getState().pdfViewer;
    // Same single pane, content swapped, mode preserved.
    expect(v?.slug).toBe("doc-b");
    expect(v?.page).toBe(1);
    expect(v?.mode).toBe("modal");
  });

  it("setPdfViewerMode flips the shared pane in place", () => {
    useUiStore.getState().openPdf("lkh", { page: 2 });
    useUiStore.getState().setPdfViewerMode("modal");
    expect(useUiStore.getState().pdfViewer?.mode).toBe("modal");
    expect(useUiStore.getState().pdfViewer?.page).toBe(2);
  });

  it("setPdfViewerMode is a no-op when no document is open", () => {
    useUiStore.getState().setPdfViewerMode("modal");
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("closePdf returns to canvas-full (no viewer)", () => {
    useUiStore.getState().openPdf("lkh");
    useUiStore.getState().closePdf();
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("setSourceDockRatio stores a ratio within the band", () => {
    useUiStore.getState().setSourceDockRatio(0.5);
    expect(useUiStore.getState().sourceDockRatio).toBe(0.5);
  });

  it("setSourceDockRatio clamps below the minimum", () => {
    useUiStore.getState().setSourceDockRatio(0.01);
    expect(useUiStore.getState().sourceDockRatio).toBe(0.2);
  });

  it("setSourceDockRatio clamps above the maximum", () => {
    useUiStore.getState().setSourceDockRatio(0.99);
    expect(useUiStore.getState().sourceDockRatio).toBe(0.8);
  });

  it("setSourceDockRatio falls back to default for non-finite input", () => {
    useUiStore.getState().setSourceDockRatio(Number.NaN);
    expect(useUiStore.getState().sourceDockRatio).toBe(DEFAULT_SOURCE_DOCK_RATIO);
  });

  it("the dock ratio persists across opening/closing the viewer", () => {
    useUiStore.getState().setSourceDockRatio(0.6);
    useUiStore.getState().openPdf("lkh");
    useUiStore.getState().closePdf();
    expect(useUiStore.getState().sourceDockRatio).toBe(0.6);
  });
});

describe("uiStore properties panel (inspector)", () => {
  it("setPropertiesOpen toggles the inspector", () => {
    useUiStore.getState().setPropertiesOpen(true);
    expect(useUiStore.getState().propertiesOpen).toBe(true);
    useUiStore.getState().setPropertiesOpen(false);
    expect(useUiStore.getState().propertiesOpen).toBe(false);
  });

  it("toggleProperties flips the inspector open/closed", () => {
    useUiStore.setState({ propertiesOpen: false });
    useUiStore.getState().toggleProperties();
    expect(useUiStore.getState().propertiesOpen).toBe(true);
    useUiStore.getState().toggleProperties();
    expect(useUiStore.getState().propertiesOpen).toBe(false);
  });
});

describe("uiStore source cluster layout (#220 part B)", () => {
  it("explorer width defaults to the documented default", () => {
    expect(useUiStore.getState().explorerWidth).toBe(DEFAULT_EXPLORER_WIDTH);
  });

  it("setExplorerWidth stores a width within the band", () => {
    useUiStore.getState().setExplorerWidth(300);
    expect(useUiStore.getState().explorerWidth).toBe(300);
  });

  it("setExplorerWidth clamps below the minimum", () => {
    useUiStore.getState().setExplorerWidth(10);
    expect(useUiStore.getState().explorerWidth).toBe(160);
  });

  it("setExplorerWidth clamps above the maximum", () => {
    useUiStore.getState().setExplorerWidth(9999);
    expect(useUiStore.getState().explorerWidth).toBe(520);
  });

  it("setExplorerWidth persists to localStorage", () => {
    const store = installLocalStorageStub();
    useUiStore.getState().setExplorerWidth(280);
    expect(store["anchor.explorerWidth"]).toBe("280");
  });

  it("source cluster is expanded by default", () => {
    expect(useUiStore.getState().sourceClusterCollapsed).toBe(false);
  });

  it("toggleSourceCluster flips and persists the collapsed flag", () => {
    const store = installLocalStorageStub();
    useUiStore.getState().toggleSourceCluster();
    expect(useUiStore.getState().sourceClusterCollapsed).toBe(true);
    expect(store["anchor.sourceClusterCollapsed"]).toBe("1");
    useUiStore.getState().toggleSourceCluster();
    expect(useUiStore.getState().sourceClusterCollapsed).toBe(false);
    expect(store["anchor.sourceClusterCollapsed"]).toBe("0");
  });

  it("setSourceClusterCollapsed persists the flag", () => {
    const store = installLocalStorageStub();
    useUiStore.getState().setSourceClusterCollapsed(true);
    expect(useUiStore.getState().sourceClusterCollapsed).toBe(true);
    expect(store["anchor.sourceClusterCollapsed"]).toBe("1");
  });
});
