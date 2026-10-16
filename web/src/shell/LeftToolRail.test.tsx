import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/stores/uiStore";
import { LeftToolRail } from "./LeftToolRail";

beforeEach(() => useUiStore.setState({ armedTool: null, navigationMode: "select", selectedNodeId: null }));
afterEach(cleanup);
describe("canvas tool shortcuts", () => {
  it("offers no hand: a drag pans, so H does nothing and V puts a tool down", () => {
    const view = render(<LeftToolRail workspaceSlug="a" />);
    expect(view.queryByRole("button", { name: "Hand" })).toBeNull();
    expect(view.queryByRole("button", { name: "Select" })).toBeNull();
    fireEvent.keyDown(window, { key: "h" });
    expect(useUiStore.getState().navigationMode).toBe("select");
    act(() => useUiStore.setState({ armedTool: "concept" }));
    fireEvent.keyDown(window, { key: "v" });
    expect(useUiStore.getState().armedTool).toBeNull();
  });

  it("keeps navigation keys in editors and source controls and preserves mark-up", () => {
    const view = render(<><LeftToolRail workspaceSlug="a" /><input aria-label="Name" />
      <aside><button>Source page</button></aside></>);
    for (const target of [view.getByLabelText("Name"), view.getByRole("button", { name: "Source page" })]) {
      fireEvent.keyDown(target, { key: "h" });
      expect(useUiStore.getState().navigationMode).toBe("select");
    }
    act(() => useUiStore.setState({ armedTool: "__intent__" }));
    fireEvent.keyDown(window, { key: "h" });
    fireEvent.keyDown(window, { key: "v" });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(useUiStore.getState().armedTool).toBe("__intent__");
  });
  it("keeps existing single-key tools and Escape back to selection", () => {
    render(<LeftToolRail workspaceSlug="a" />);
    fireEvent.keyDown(window, { key: "r" });
    expect(useUiStore.getState().armedTool).toBe("concept");
    fireEvent.keyDown(window, { key: "t" });
    expect(useUiStore.getState().armedTool).toBe("text");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(useUiStore.getState().armedTool).toBeNull();
  });
  it("keeps tool letters and Escape native in select and nested text editors", () => {
    const view = render(<><LeftToolRail workspaceSlug="a" /><select aria-label="Display"><option>Compact</option></select>
      <div role="textbox" contentEditable suppressContentEditableWarning><span data-testid="body">Type here</span></div></>);
    useUiStore.setState({ armedTool: "concept" });
    for (const target of [view.getByLabelText("Display"), view.getByTestId("body")]) {
      fireEvent.keyDown(target, { key: "t" });
      expect(useUiStore.getState().armedTool).toBe("concept");
      fireEvent.keyDown(target, { key: "Escape" });
      expect(useUiStore.getState().armedTool).toBe("concept");
    }
  });
});
