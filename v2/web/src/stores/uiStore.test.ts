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
    propertiesOpen: false,
    dropTargetAreaId: null,
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
