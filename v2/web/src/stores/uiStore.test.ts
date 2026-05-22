/**
 * uiStore unit tests — pinning the armed-tool state transitions and the
 * mutual exclusion between the Library drawer and the Properties panel.
 *
 * Why this test exists: the left tool rail relies on `armedTool` being a
 * predictable single source of truth. A bug where clicking the same icon
 * twice fails to disarm, or where arming a tool leaves a stale value
 * around, would make the canvas un-clickable. Pin both gestures.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useUiStore } from "./uiStore";

beforeEach(() => {
  // Reset to the initial state by setting every field individually — the
  // store has no `reset()` action.
  useUiStore.setState({
    pdfViewer: null,
    hoveredSourceRef: null,
    libraryDrawerOpen: false,
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

describe("uiStore mutual exclusion (library vs properties)", () => {
  it("opening Properties closes the Library drawer", () => {
    useUiStore.setState({ libraryDrawerOpen: true });
    useUiStore.getState().setPropertiesOpen(true);
    const s = useUiStore.getState();
    expect(s.propertiesOpen).toBe(true);
    expect(s.libraryDrawerOpen).toBe(false);
  });

  it("toggleProperties on closes the Library drawer", () => {
    useUiStore.setState({ libraryDrawerOpen: true, propertiesOpen: false });
    useUiStore.getState().toggleProperties();
    const s = useUiStore.getState();
    expect(s.propertiesOpen).toBe(true);
    expect(s.libraryDrawerOpen).toBe(false);
  });
});
