import { afterEach, expect, it } from "vitest";
import { canvasNavigation, navigationKey } from "./canvasNavigation";

afterEach(() => { document.body.innerHTML = ""; });

function keyAt(target: EventTarget, key: string, options: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options });
  target.dispatchEvent(event);
  return navigationKey(event);
}

it("owns only unmodified navigation keys on canvas or its rail", () => {
  document.body.innerHTML = '<div class="react-flow"><div class="react-flow__node" tabindex="0"></div></div><div role="toolbar" aria-label="Canvas tools"><button>Hand</button></div>';
  const node = document.querySelector(".react-flow__node")!;
  expect(keyAt(window, "h")).toBe("hand");
  expect(keyAt(node, "h")).toBe("hand");
  expect(keyAt(document.querySelector("button")!, "v")).toBe("select");
  for (const modifier of [{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }]) {
    expect(keyAt(node, "h", modifier)).toBeNull();
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
