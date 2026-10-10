import { afterEach, describe, expect, it } from "vitest";
import { editorAction, planNudge } from "./editorShortcuts";
import type { ClipboardNode } from "./clipboard";

afterEach(() => { document.body.innerHTML = ""; });
function action(key: string, html = '<div class="react-flow"><div class="react-flow__node" data-id="a" tabindex="0"></div></div>', modifiers = {}) {
  document.body.innerHTML = html;
  let result;
  const target = document.body.querySelector("[tabindex], input, button, select, textarea, [role=textbox]")!;
  target.addEventListener("keydown", (event) => { result = editorAction(event as KeyboardEvent); });
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...modifiers }));
  return result;
}
describe("editor keyboard ownership", () => {
  it("renames the focused node and keeps the existing 5/20 pixel arrow steps", () => {
    expect(action("Enter")).toEqual({ type: "rename", nodeId: "a" });
    expect(action("ArrowRight")).toEqual({ type: "nudge", nodeId: "a", dx: 5, dy: 0 });
    expect(action("ArrowUp", undefined, { shiftKey: true })).toEqual({ type: "nudge", nodeId: "a", dx: 0, dy: -20 });
    expect(action("d", undefined, { ctrlKey: true })).toEqual({ type: "duplicate" });
    expect(action("d", undefined, { metaKey: true })).toEqual({ type: "duplicate" });
  });
  it.each(["<input>", "<textarea></textarea>", "<select></select>", '<div role="textbox" contenteditable><span tabindex="0">body</span></div>'])("leaves text editors alone: %s", (field) => {
    const html = `<div class="react-flow"><div class="react-flow__node" data-id="a">${field}</div></div>`;
    expect(action("Enter", html)).toBeNull();
    expect(action("ArrowRight", html)).toBeNull();
    expect(action("d", html, { ctrlKey: true })).toBeNull();
  });
  it("leaves source viewer navigation, focused buttons, and modified arrows untouched", () => {
    expect(action("ArrowRight", '<div tabindex="0" aria-label="PDF source"></div>')).toBeNull();
    expect(action("Enter", '<div class="react-flow"><div class="react-flow__node" data-id="a"><button>Details</button></div></div>')).toBeNull();
    expect(action("ArrowRight", undefined, { ctrlKey: true })).toBeNull();
    expect(action("d", undefined, { ctrlKey: true, shiftKey: true })).toBeNull();
    expect(action("Enter", undefined, { altKey: true })).toBeNull();
  });
});

describe("canonical nudge plan", () => {
  const nodes: Record<string, ClipboardNode> = {
    parent: { id: "parent", node_type: "area", label: "Group", x: 100, y: 100 },
    nested: { id: "nested", node_type: "area", label: "Nested", x: 125, y: 130, parent: "parent" },
    child: { id: "child", node_type: "fact", label: "Fact", x: 140, y: 150, parent: "nested", data: { collapsed: true } },
    locked: { id: "locked", node_type: "fact", label: "Locked", x: 300, y: 300, locked: true },
  };
  it("moves nested descendants once even when parent and child are both selected", () => {
    const before = structuredClone(nodes);
    expect(planNudge(nodes, ["parent", "child"], 5, 0)).toEqual([
      { id: "parent", x: 105, y: 100 }, { id: "child", x: 145, y: 150 }, { id: "nested", x: 130, y: 130 },
    ]);
    expect(nodes).toEqual(before);
  });
  it("moves a selected child in absolute coordinates without changing its parent", () => {
    expect(planNudge(nodes, ["child"], 0, -20)).toEqual([{ id: "child", x: 140, y: 130 }]);
    expect(nodes.child!.parent).toBe("nested");
  });
  it("ignores missing and locked roots but moves a locked child with its container", () => {
    expect(planNudge(nodes, ["missing", "locked"], 5, 0)).toEqual([]);
    const grouped = { ...nodes, locked: { ...nodes.locked!, parent: "parent" } };
    expect(planNudge(grouped, ["parent"], 5, 0)).toContainEqual({ id: "locked", x: 305, y: 300 });
  });
  it("terminates on malformed parent cycles and does not double the movement", () => {
    const cyclic = { ...nodes, parent: { ...nodes.parent!, parent: "nested" } };
    expect(planNudge(cyclic, ["parent", "nested"], 5, 0)).toHaveLength(3);
  });
});
