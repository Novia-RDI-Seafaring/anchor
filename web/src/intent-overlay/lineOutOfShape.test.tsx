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

it("leaves no dot behind for a wobble in place", async () => {
  render(<Host />); await act(async () => {});
  const before = screen.getByTestId("comment-lasso-ink").querySelectorAll("polyline").length;
  // A long path that never goes anywhere: back and forth over three pixels.
  draw([[400, 400], [403, 401], [400, 402], [403, 400], [400, 401], [403, 402], [401, 400]]);
  expect(screen.getByTestId("comment-lasso-ink").querySelectorAll("polyline").length).toBe(before);
});

it("takes the line back when Escape leaves its label unwritten", async () => {
  render(<Host />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const first = screen.getByTestId("comment-lasso-note");
  fireEvent.change(first, { target: { value: "PX-5" } });
  fireEvent.keyDown(first, { key: "Enter" });
  const lines = () => screen.getByTestId("comment-lasso-ink").querySelectorAll("polyline").length;
  const withBox = lines();
  draw([[420, 380], [520, 360], [620, 330], [720, 320]]);
  expect(lines()).toBeGreaterThan(withBox);
  const offered = screen.getAllByTestId("comment-lasso-note").at(-1)!;
  fireEvent.keyDown(offered, { key: "Escape" });
  expect(lines()).toBe(withBox);
  // The box and its words stay.
  expect((screen.getAllByTestId("comment-lasso-note") as HTMLTextAreaElement[]).map((n) => n.value)).toEqual(["PX-5"]);
});

it("deletes a line with its label when the label is picked out and deleted", async () => {
  render(<Host />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const first = screen.getByTestId("comment-lasso-note");
  fireEvent.change(first, { target: { value: "PX-5" } });
  fireEvent.keyDown(first, { key: "Enter" });
  const lines = () => screen.getByTestId("comment-lasso-ink").querySelectorAll("polyline").length;
  const withBox = lines();
  draw([[420, 380], [520, 360], [620, 330], [720, 320]]);
  const label = screen.getAllByTestId("comment-lasso-note").at(-1)!;
  fireEvent.change(label, { target: { value: "specs" } });
  fireEvent.keyDown(label, { key: "Enter" });
  // Pick the label out (press and let go on its words), then delete.
  const words = screen.getAllByTestId("comment-lasso-note").at(-1)!;
  fireEvent.pointerDown(words, { clientX: 730, clientY: 320, button: 0, pointerId: 2 });
  fireEvent.pointerUp(words, { clientX: 730, clientY: 320, button: 0, pointerId: 2 });
  fireEvent.keyDown(window, { key: "Delete" });
  expect(lines()).toBe(withBox);
  expect((screen.getAllByTestId("comment-lasso-note") as HTMLTextAreaElement[]).map((n) => n.value)).toEqual(["PX-5"]);
});

it("offers a label at the end of a line drawn out of a sent remark, either way", async () => {
  const filed = { id: "r1", status: "pending", created_at: 1, targetIds: [], payload: {}, items: [] };
  function SendingHost() {
    const viewport = { x: 0, y: 0, zoom: 1 };
    const host: OverlayHost = {
      geometry: { boxes: [], viewport, getViewport: () => viewport, setViewport: vi.fn(),
        screenToWorld: (p) => p, rowsOf: () => [], edgesOf: () => [] },
      display: { labelOf: () => "", preview: () => ({ nodes: [], edges: [] }) },
      thread: {
        loadScoped: vi.fn(async () => []), get: vi.fn(async () => filed),
        submit: vi.fn(async (remark: unknown) => ({ ...filed, payload: remark })),
        subscribeChanged: vi.fn(() => () => {}),
        addItem: vi.fn(), answer: vi.fn(), apply: vi.fn(), revert: vi.fn(), decline: vi.fn(), resolve: vi.fn(),
      } as unknown as OverlayHost["thread"],
    };
    return <div style={{ position: "relative", width: 1000, height: 1000 }}><IntentOverlay active host={host} /></div>;
  }
  render(<SendingHost />); await act(async () => {});
  draw([[300, 300], [500, 300], [500, 450], [300, 450], [300, 300]]);
  const first = screen.getByTestId("comment-lasso-note");
  fireEvent.change(first, { target: { value: "PX-10" } });
  fireEvent.keyDown(first, { key: "Enter" });
  await act(async () => { fireEvent.click(screen.getByTestId("comment-lasso-send")); });
  // The box is on the board now, not in the remark being drawn. A line out
  // of it to the left still gets somewhere to write.
  draw([[320, 380], [250, 400], [180, 450], [120, 520]]);
  const notes = screen.getAllByTestId("comment-lasso-note") as HTMLTextAreaElement[];
  expect(notes.at(-1)!.value).toBe("");
  expect(notes.at(-1)).toBe(document.activeElement);
});
