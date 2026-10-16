import { afterEach, expect, it } from "vitest";
import { canvasNavigation, navigationKey, navigationNodes } from "./canvasNavigation";

afterEach(() => { document.body.innerHTML = ""; });

function keyAt(target: EventTarget, key: string, options: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options });
  target.dispatchEvent(event);
  return navigationKey(event);
}

it("owns only unmodified navigation keys on canvas or its rail", () => {
  document.body.innerHTML = '<div class="react-flow"><div class="react-flow__node" tabindex="0"></div></div><div role="toolbar" aria-label="Canvas tools"><button>Hand</button></div>';
  const node = document.querySelector(".react-flow__node")!;
  // There is no hand mode: H is not a navigation key.
  expect(keyAt(window, "h")).toBeNull();
  expect(keyAt(node, "v")).toBe("select");
  expect(keyAt(document.querySelector("button")!, "v")).toBe("select");
  for (const modifier of [{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }]) {
    expect(keyAt(node, "v", modifier)).toBeNull();
  }
});

it("does not steal source controls, text, dialogs, or read-only canvases", () => {
  document.body.innerHTML = '<aside><button>Page</button><input /></aside><div role="dialog"><div class="react-flow">Preview</div></div><div data-canvas-read-only="true"><div class="react-flow">Monitor</div></div><div class="react-flow"><button>Open source</button><div contenteditable="true"><span>Text</span></div></div>';
  for (const target of document.querySelectorAll('button, input, [role="dialog"] .react-flow, [data-canvas-read-only] .react-flow, span')) {
    expect(keyAt(target, "h")).toBeNull();
  }
});

it("pans on a background drag, leaves selection to Shift, and keeps alternate-button pan for armed tools", () => {
  expect(canvasNavigation("select", false, null)).toMatchObject({ hand: false, selectionOnDrag: false, panOnDrag: true });
  expect(canvasNavigation("hand", false, null)).toMatchObject({ hand: true, selectionOnDrag: false, panOnDrag: true });
  expect(canvasNavigation("hand", true, null)).toMatchObject({ hand: false, selectionOnDrag: false, panOnDrag: true });
  expect(canvasNavigation("hand", false, "concept")).toMatchObject({ hand: false, selectionOnDrag: false, panOnDrag: [1, 2] });
});

it("keeps an area's explicit drag override from sharing an armed gesture", () => {
  const nodes = [
    { id: "area", draggable: true, selected: true },
    { id: "locked", draggable: false },
    { id: "ordinary" },
  ];
  for (const tool of ["concept", "area", "text", "canvas", "connect", "intent"]) {
    const navigation = canvasNavigation("select", false, tool);
    expect(navigation.nodesDraggable).toBe(false);
    expect(navigationNodes(nodes, navigation).map((node) => node.draggable)).toEqual([false, false, false]);
    expect(navigationNodes(nodes, navigation)[0]?.selected).toBe(true);
    expect(navigation.panOnDrag).toEqual([1, 2]);
  }
  // Select restores each node's original policy, including explicit locks.
  const select = canvasNavigation("select", false, null);
  expect(select.nodesDraggable).toBe(true);
  expect(navigationNodes(nodes, select)).toBe(nodes);
  expect(nodes[0]?.draggable).toBe(true);
});

it("prevents explicit per-node dragging in Hand and read-only modes", () => {
  const nodes = [{ id: "area", draggable: true, selected: true }];
  const hand = canvasNavigation("hand", false, null);
  expect(navigationNodes(nodes, hand)[0]).toMatchObject({ draggable: false, selected: false });
  expect(hand.panOnDrag).toBe(true);
  const readOnly = canvasNavigation("select", true, null);
  expect(readOnly.nodesDraggable).toBe(false);
  expect(navigationNodes(nodes, readOnly)[0]?.draggable).toBe(false);
});

it("pans instead of moving a card while space is held", () => {
  const nodes: { id: string; draggable?: boolean }[] = [{ id: "card" }];
  const held = canvasNavigation("select", false, null, true);
  expect(held.nodesDraggable).toBe(false);
  expect(held.panOnDrag).toBe(true);
  expect(navigationNodes(nodes, held)[0]?.draggable).toBe(false);
  expect(canvasNavigation("select", false, null, false).nodesDraggable).toBe(true);
});
