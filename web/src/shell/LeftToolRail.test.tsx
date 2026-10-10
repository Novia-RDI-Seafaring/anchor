import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/stores/uiStore";
import { LeftToolRail } from "./LeftToolRail";

beforeEach(() => useUiStore.setState({ armedTool: null, selectedNodeId: null }));
afterEach(cleanup);
describe("canvas tool shortcuts", () => {
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
