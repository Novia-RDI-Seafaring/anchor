import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { IntentOverlay, type OverlayHost } from "./index";

vi.mock("@/api/intents", () => ({}));

function Host() {
  const viewport = { x: 0, y: 0, zoom: 1 };
  const host: OverlayHost = {
    geometry: { boxes: [], viewport, getViewport: () => viewport, setViewport: vi.fn(),
      screenToWorld: (p) => p, rowsOf: () => [], edgesOf: () => [] },
    display: { labelOf: () => "", preview: () => ({ nodes: [], edges: [] }) },
    thread: {
      loadScoped: vi.fn(async () => []), get: vi.fn(), submit: vi.fn(), subscribeChanged: vi.fn(() => () => {}),
      addItem: vi.fn(), answer: vi.fn(), apply: vi.fn(), revert: vi.fn(), decline: vi.fn(), resolve: vi.fn(),
    } as unknown as OverlayHost["thread"],
  };
  return <div style={{ position: "relative", width: 1000, height: 1000 }}><IntentOverlay active host={host} /></div>;
}

beforeEach(() => {
  vi.stubGlobal("PointerEvent", MouseEvent);
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(() => new DOMRect(0, 0, 1000, 1000));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function draw(points: [number, number][]) {
  const surface = screen.getByTestId("comment-lasso-surface");
  const at = ([x, y]: [number, number]) => ({ clientX: x, clientY: y, button: 0, pointerId: 1 });
  fireEvent.pointerDown(surface, at(points[0]!));
  for (const p of points.slice(1)) fireEvent.pointerMove(surface, at(p));
  fireEvent.pointerUp(surface, at(points.at(-1)!));
}

it("offers a label at the end of a line drawn out of a labelled box", async () => {
  render(<Host />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const first = screen.getByTestId("comment-lasso-note");
  fireEvent.change(first, { target: { value: "PX-5" } });
  fireEvent.keyDown(first, { key: "Enter" });
  draw([[420, 380], [520, 360], [620, 330], [720, 320]]);
  const notes = screen.getAllByTestId("comment-lasso-note");
  expect(notes.length).toBe(2);
});

it("offers a label at the end of the line while the box's words are still being typed", async () => {
  render(<Host />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const first = screen.getByTestId("comment-lasso-note");
  fireEvent.change(first, { target: { value: "PX-5" } });
  draw([[420, 380], [520, 360], [620, 330], [720, 320]]);
  expect(screen.getAllByTestId("comment-lasso-note").length).toBe(2);
});

it("offers a label at the end of a line drawn out of an empty box", async () => {
  render(<Host />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  draw([[420, 380], [520, 360], [620, 330], [720, 320]]);
  expect(screen.getAllByTestId("comment-lasso-note").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByTestId("comment-lasso-note").at(-1)).toBe(document.activeElement);
});

it("is not blocked by an empty label left behind by an earlier stroke", async () => {
  render(<Host />); await act(async () => {});
  // A box drawn and left without words, then a box with words and a line
  // out of it.
  draw([[100, 700], [300, 700], [300, 850], [100, 850], [100, 700]]);
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const typed = screen.getAllByTestId("comment-lasso-note").at(-1)!;
  fireEvent.change(typed, { target: { value: "PX-5" } });
  fireEvent.keyDown(typed, { key: "Enter" });
  draw([[420, 380], [520, 360], [620, 330], [720, 320]]);
  const notes = screen.getAllByTestId("comment-lasso-note") as HTMLTextAreaElement[];
  // The box keeps its words; the line gets an empty field, focused to type in.
  expect(notes.map((n) => n.value)).toContain("PX-5");
  const fresh = notes.at(-1)!;
  expect(fresh.value).toBe("");
  expect(fresh).toBe(document.activeElement);
});

it("moves the canvas so the words at the end of a line drawn to the edge can be seen", async () => {
  const setViewport = vi.fn();
  function EdgeHost() {
    const viewport = { x: 0, y: 0, zoom: 1 };
    const host: OverlayHost = {
      geometry: { boxes: [], viewport, getViewport: () => viewport, setViewport,
        screenToWorld: (p) => p, rowsOf: () => [], edgesOf: () => [] },
      display: { labelOf: () => "", preview: () => ({ nodes: [], edges: [] }) },
      thread: {
        loadScoped: vi.fn(async () => []), get: vi.fn(), submit: vi.fn(), subscribeChanged: vi.fn(() => () => {}),
        addItem: vi.fn(), answer: vi.fn(), apply: vi.fn(), revert: vi.fn(), decline: vi.fn(), resolve: vi.fn(),
      } as unknown as OverlayHost["thread"],
    };
    return <div style={{ position: "relative", width: 1000, height: 1000 }}><IntentOverlay active host={host} /></div>;
  }
  render(<EdgeHost />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const first = screen.getByTestId("comment-lasso-note");
  fireEvent.change(first, { target: { value: "PX-5" } });
  fireEvent.keyDown(first, { key: "Enter" });
  setViewport.mockClear();
  draw([[420, 380], [700, 360], [990, 350]]);
  // The words run right from x 990; the window ends at 1000 (less the
  // rails' inset), so the canvas moves left by the overflow.
  expect(setViewport).toHaveBeenCalledTimes(1);
  const moved = setViewport.mock.calls[0]![0] as { x: number; y: number; zoom: number };
  expect(moved.x).toBeLessThan(0);
  expect(moved.y).toBe(0);
});
