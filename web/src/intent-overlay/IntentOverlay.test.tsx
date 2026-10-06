import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useLayoutEffect, useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IntentOverlay, type Intent, type OverlayHost, type ThreadItem } from "./index";

// A accidental application import would fail before this ordinary DOM host mounts.
vi.mock("@/api/intents", () => { throw new Error("independent host imported Anchor API"); });
vi.mock("@/stores/canvasStore", () => { throw new Error("independent host imported canvas store"); });
vi.mock("@xyflow/react", () => { throw new Error("independent host imported ReactFlow"); });

const id = "account/email";
const question: ThreadItem = { id: "q", type: "question", author: { kind: "agent" },
  text: "Which email?", options: ["Work", "Home"], created_at: 2, state: "open" };
const suggestion: ThreadItem = { id: "s", type: "suggestion", author: { kind: "agent" },
  text: "Use work email", created_at: 3, state: "pending", ops: [{ type: "FieldSet" }] };
function thread(items: ThreadItem[] = []): Intent {
  return { id: "request", status: "pending", created_at: 1, targetIds: [id],
    payload: { text: "Check this email" }, items };
}
function fixture(initial: Intent[] = []) {
  let current = initial[0] ?? thread();
  let changed = () => {};
  const unsubscribe = vi.fn();
  const threadPort: OverlayHost["thread"] = {
    loadScoped: vi.fn(async () => initial),
    get: vi.fn(async () => current),
    submit: vi.fn(async (remark) => {
      current = { ...thread(), targetIds: remark.targetIds, payload: remark };
      return current;
    }),
    subscribeChanged: vi.fn((listener) => { changed = listener; return unsubscribe; }),
    addItem: vi.fn(async () => suggestion), answer: vi.fn(async () => question),
    apply: vi.fn(async () => suggestion), revert: vi.fn(async () => suggestion),
    decline: vi.fn(async () => suggestion), resolve: vi.fn(async () => undefined),
  };
  return { threadPort, unsubscribe, notify: () => changed(), replace: (value: Intent) => { current = value; } };
}

function Form({ api, active = true }: { api: ReturnType<typeof fixture>; active?: boolean }) {
  const ref = useRef<HTMLFormElement>(null);
  const [boxes, setBoxes] = useState<OverlayHost["geometry"]["boxes"]>([]);
  const [value, setValue] = useState("old@example.test");
  const viewport = { x: 20, y: 10, zoom: 2 };
  useLayoutEffect(() => {
    setBoxes(Array.from(ref.current!.querySelectorAll<HTMLElement>("[data-intent-id]")).map((field) => {
      const rect = field.getBoundingClientRect();
      return { id: field.dataset.intentId!, x: (rect.left - 20) / 2, y: (rect.top - 10) / 2,
        width: rect.width / 2, height: rect.height / 2 };
    }));
  }, []);
  const host: OverlayHost = {
    geometry: { boxes, viewport, getViewport: () => viewport, setViewport: vi.fn(),
      screenToWorld: (p) => ({ x: (p.x - 20) / 2, y: (p.y - 10) / 2 }),
      rowsOf: () => [{ key: "one", top: 100, bottom: 130 }, { key: "two", top: 130, bottom: 180 }],
      edgesOf: () => [{ id: "email->flow", source: id, target: "max_flow", points: [{ x: 400, y: 400 }, { x: 600, y: 400 }] }],
    },
    display: {
      labelOf: (target) => target === id ? "Email" : "Maximum flow",
      // This is inert host output. The renderer does not inspect FieldSet.
      preview: () => ({ nodes: [{ id, kind: "updated", x: 100, y: 100, width: 100, height: 80,
        label: "Email", rows: [{ key: "address", value: "work@example.test" }] }], edges: [] }),
    },
    thread: api.threadPort,
  };
  // Keep the transport stable so rerenders do not restart scoped loading/polls.
  api.threadPort.apply = vi.fn(async () => {
    setValue("work@example.test");
    api.replace(thread([{ ...suggestion, state: "applied" }]));
    api.notify();
    return suggestion;
  });
  api.threadPort.revert = vi.fn(async () => {
    setValue("old@example.test");
    api.replace(thread([{ ...suggestion, state: "reverted" }]));
    api.notify();
    return suggestion;
  });
  return <div style={{ position: "relative", width: 1000, height: 1000 }}>
    <form ref={ref}><label>Email<input aria-label="Email" data-intent-id={id} value={value}
      onChange={(e) => setValue(e.target.value)} /></label></form>
    <IntentOverlay active={active} host={host} />
  </div>;
}

const originalCapture = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "setPointerCapture");
beforeEach(() => {
  vi.stubGlobal("PointerEvent", MouseEvent);
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return this.dataset.intentId ? new DOMRect(220, 210, 200, 160) : new DOMRect(0, 0, 1000, 1000);
  });
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  if (originalCapture) Object.defineProperty(HTMLElement.prototype, "setPointerCapture", originalCapture);
  else Reflect.deleteProperty(HTMLElement.prototype, "setPointerCapture");
});
function draw(points: [number, number][]) {
  const surface = screen.getByTestId("comment-lasso-surface");
  const event = ([x, y]: [number, number]) => ({ clientX: x * 2 + 20, clientY: y * 2 + 10, button: 0, pointerId: 1 });
  fireEvent.pointerDown(surface, event(points[0]!));
  for (const point of points.slice(1)) fireEvent.pointerMove(surface, event(point));
  fireEvent.pointerUp(surface, event(points.at(-1)!));
}
const ring: [number, number][] = [[80, 80], [150, 75], [220, 80], [225, 140], [220, 200], [150, 205], [80, 200], [75, 140], [80, 80]];

describe("independent DOM intent overlay", () => {
  it("measures ordinary fields, preserves opaque targets and ink across active toggles, and submits host coordinates", async () => {
    const api = fixture();
    const view = render(<Form api={api} />);
    await act(async () => {});
    draw(ring);
    expect(screen.getByTestId("comment-lasso-ids").textContent).toContain(id);
    const note = screen.getByTestId("comment-lasso-note");
    fireEvent.change(note, { target: { value: "Check address" } });
    fireEvent.keyDown(note, { key: "Enter" });
    view.rerender(<Form api={api} active={false} />);
    expect(screen.queryByTestId("comment-lasso-ink")).toBeNull();
    view.rerender(<Form api={api} />);
    expect(screen.getByTestId("comment-lasso-ids").textContent).toContain(id);
    fireEvent.click(screen.getByTestId("comment-lasso-send"));
    await waitFor(() => expect(api.threadPort.submit).toHaveBeenCalledOnce());
    expect(api.threadPort.submit).toHaveBeenCalledWith(expect.objectContaining({
      targetIds: [id], sketch: expect.objectContaining({ nodes: [expect.objectContaining({ encircles: id })] }),
    }));
    expect(api.threadPort.loadScoped).toHaveBeenCalledOnce();
  });

  it("restores a scoped thread, answers options, previews without writing, and applies/reverts through the form host", async () => {
    const api = fixture([thread([question, suggestion])]);
    const view = render(<Form api={api} />);
    await screen.findByTestId("comment-lasso-preview-node");
    expect((screen.getByRole("textbox", { name: "Email" }) as HTMLInputElement).value).toBe("old@example.test");
    fireEvent.click(screen.getByRole("button", { name: "Work" }));
    expect(api.threadPort.answer).toHaveBeenCalledWith("request", "q", "Work");
    fireEvent.click(screen.getByTestId("comment-lasso-approve"));
    await screen.findByTestId("comment-lasso-revert");
    expect((screen.getByRole("textbox", { name: "Email" }) as HTMLInputElement).value).toBe("work@example.test");
    fireEvent.click(screen.getByTestId("comment-lasso-revert"));
    await waitFor(() => expect((screen.getByRole("textbox", { name: "Email" }) as HTMLInputElement).value).toBe("old@example.test"));
    view.unmount();
    expect(api.unsubscribe).toHaveBeenCalledOnce();
  });

  it("uses host-supplied row and edge geometry with unchanged two-stroke cross semantics", async () => {
    const api = fixture(); render(<Form api={api} />); await act(async () => {});
    draw([[80, 130], [150, 130], [220, 130]]);
    expect(screen.getByTestId("comment-lasso-cuts").textContent).toContain("Email");
    draw([[470, 370], [500, 400], [530, 430]]);
    expect(screen.queryByTestId("comment-lasso-strikes")).toBeNull();
    draw([[530, 370], [500, 400], [470, 430]]);
    fireEvent.click(screen.getByTestId("comment-lasso-send"));
    await waitFor(() => expect(api.threadPort.submit).toHaveBeenCalledOnce());
    expect(api.threadPort.submit).toHaveBeenCalledWith(expect.objectContaining({
      targetIds: [id, "max_flow"],
      cuts: [expect.objectContaining({ node: id, after: "one" })],
      strikes: [expect.objectContaining({ edge: "email->flow", source: id, target: "max_flow" })],
    }));
  });
});
