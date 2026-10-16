import { afterEach, describe, expect, it } from "vitest";
import { isCanvasSelectAll } from "./clipboard";

const press = (target: EventTarget, init: KeyboardEventInit = { key: "a", metaKey: true }) => {
  let seen: KeyboardEvent | null = null;
  target.addEventListener("keydown", (e) => { seen = e as KeyboardEvent; }, { once: true });
  target.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, ...init }));
  return seen!;
};

describe("isCanvasSelectAll", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("claims Cmd/Ctrl+A on the page and on the canvas", () => {
    document.body.innerHTML = '<div class="react-flow"><div class="react-flow__node" tabindex="0"></div></div>';
    expect(isCanvasSelectAll(press(document.body))).toBe(true);
    expect(isCanvasSelectAll(press(document.querySelector(".react-flow__node")!, { key: "a", ctrlKey: true }))).toBe(true);
  });

  it("leaves fields, viewers, dialogs and other keys to the browser", () => {
    document.body.innerHTML = '<input /><aside><p tabindex="0">page</p></aside><div role="dialog"><p tabindex="0">x</p></div><div class="react-flow" tabindex="0"></div>';
    expect(isCanvasSelectAll(press(document.querySelector("input")!))).toBe(false);
    expect(isCanvasSelectAll(press(document.querySelector("aside p")!))).toBe(false);
    expect(isCanvasSelectAll(press(document.querySelector('[role="dialog"] p')!))).toBe(false);
    expect(isCanvasSelectAll(press(document.querySelector(".react-flow")!, { key: "a" }))).toBe(false);
    expect(isCanvasSelectAll(press(document.querySelector(".react-flow")!, { key: "a", metaKey: true, shiftKey: true }))).toBe(false);
  });
});
