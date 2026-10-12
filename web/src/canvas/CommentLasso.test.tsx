import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { intents, type Intent, type ThreadItem } from "@/api/intents";
import { useCanvasStore } from "@/stores/canvasStore";
import { CommentLasso } from "./CommentLasso";

const flow = vi.hoisted(() => ({
  viewport: { x: 0, y: 0, zoom: 1 },
  getViewport: vi.fn(), setViewport: vi.fn(), screenToFlowPosition: vi.fn(),
}));
vi.mock("@xyflow/react", () => ({
  useReactFlow: () => flow,
  useViewport: () => flow.viewport,
}));
vi.mock("@/api/intents", () => ({
  INTENTS_CHANGED_EVENT: "anchor:intents-changed",
  intents: { listPending: vi.fn(), get: vi.fn(), create: vi.fn(), answer: vi.fn(),
    addItem: vi.fn(), apply: vi.fn(), revert: vi.fn(), decline: vi.fn(), resolve: vi.fn() },
}));

const originalPointerCapture = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "setPointerCapture");

const boxes = [{ id: "pump", x: 100, y: 100, width: 100, height: 80 }];
const ring: [number, number][] = [[80, 80], [150, 75], [220, 80], [225, 140], [220, 200], [150, 205], [80, 200], [75, 140], [80, 80]];
const baseIntent = (id = "ask"): Intent => ({ id, kind: "user_request", origin_canvas_id: "study",
  target: null, payload: { text: "Check the pump" }, status: "pending", created_at: 1,
  targets: [{ workspace_id: "study", node_id: "pump" }], items: [] });

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("PointerEvent", MouseEvent);
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: vi.fn() });
  flow.viewport = { x: 0, y: 0, zoom: 1 };
  flow.getViewport.mockImplementation(() => flow.viewport);
  flow.screenToFlowPosition.mockImplementation(({ x, y }) => ({
    x: (x - flow.viewport.x) / flow.viewport.zoom, y: (y - flow.viewport.y) / flow.viewport.zoom,
  }));
  vi.mocked(intents.listPending).mockResolvedValue([]);
  vi.mocked(intents.get).mockResolvedValue(baseIntent());
  vi.mocked(intents.create).mockResolvedValue(baseIntent());
  vi.mocked(intents.answer).mockResolvedValue({} as ThreadItem);
  useCanvasStore.setState({ nodes: { pump: { id: "pump", node_type: "concept", label: "Pump", x: 100, y: 100 } }, edges: {} });
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  if (originalPointerCapture) Object.defineProperty(HTMLElement.prototype, "setPointerCapture", originalPointerCapture);
  else Reflect.deleteProperty(HTMLElement.prototype, "setPointerCapture");
});

async function mount() {
  const onExit = vi.fn();
  const onFiled = vi.fn();
  const underHover = vi.fn();
  const view = (active: boolean) => <div className="react-flow">
    <button data-testid="underlying-node" onMouseEnter={underHover}>Pump</button>
    <CommentLasso active={active} boxes={boxes} workspaceSlug="study" onExit={onExit} onFiled={onFiled} />
  </div>;
  const result = render(view(true));
  const setActive = async (active: boolean) => { await act(async () => { result.rerender(view(active)); }); };
  await act(async () => {});
  return { ...result, onExit, onFiled, underHover, setActive };
}
function draw(points: [number, number][], surface = screen.getByTestId("comment-lasso-surface")) {
  const event = ([clientX, clientY]: [number, number]) => ({ clientX, clientY, button: 0, pointerId: 1 });
  fireEvent.pointerDown(surface, event(points[0]!));
  for (const point of points.slice(1)) fireEvent.pointerMove(surface, event(point));
  fireEvent.pointerUp(surface, event(points.at(-1)!));
}
function marks() { return Array.from(screen.getByTestId("comment-lasso-ink").querySelectorAll("polyline")); }
function label(text = "Check this value") {
  const note = screen.getByTestId("comment-lasso-note") as HTMLTextAreaElement;
  fireEvent.change(note, { target: { value: text } });
  fireEvent.keyDown(note, { key: "Enter" });
  return note;
}

describe("CommentLasso interactions", () => {
  it("rings a node, offers a label and draws its leader", async () => {
    await mount(); draw(ring);
    expect(marks()).toHaveLength(1);
    expect(marks()[0]!.getAttribute("fill")).not.toBe("none");
    expect(screen.getByTestId("comment-lasso-ids").textContent).toContain("pump");
    expect(screen.getByTestId("comment-lasso-note")).toBe(document.activeElement);
    expect(screen.getByTestId("comment-lasso-leader")).toBeTruthy();
    label();
    expect(screen.getByTestId("comment-lasso-note")).not.toBe(document.activeElement);
  });

  it("maps pointer coordinates through the host viewport before resolving targets", async () => {
    flow.viewport = { x: 40, y: 30, zoom: 2 };
    await mount(); draw(ring.map(([x, y]) => [x * 2 + 40, y * 2 + 30]));
    expect(screen.getByTestId("comment-lasso-ids").textContent).toContain("pump");
    expect(marks()[0]!.getAttribute("points")).toContain("200,190");
  });

  it("keeps Shift+Enter as a newline, commits with Esc and leaves ink when exiting", async () => {
    const { onExit } = await mount(); draw(ring);
    const note = screen.getByTestId("comment-lasso-note") as HTMLTextAreaElement;
    const user = userEvent.setup();
    await user.keyboard("First");
    await user.keyboard("{Shift>}{Enter}{/Shift}Second");
    expect(note.value).toBe("First\nSecond");
    expect(document.activeElement).toBe(note);
    fireEvent.keyDown(note, { key: "Escape" });
    expect(document.activeElement).not.toBe(note);
    expect(onExit).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onExit).toHaveBeenCalledOnce();
    expect(marks()).toHaveLength(1);
    expect(note.value).toBe("First\nSecond");
  });

  it.each(["ring", "label"])("deleting the %s also removes its linked label, leader and ring", async (part) => {
    await mount(); draw(ring); label();
    if (part === "ring") {
      fireEvent.pointerMove(screen.getByTestId("comment-lasso-surface"), { clientX: 80, clientY: 80, button: 0 });
      fireEvent.click(screen.getByTestId("comment-lasso-erase"));
    } else {
      const note = screen.getByTestId("comment-lasso-note");
      fireEvent.pointerDown(note, { clientX: 250, clientY: 140, button: 0 });
      fireEvent.pointerUp(note, { clientX: 250, clientY: 140, button: 0 });
      fireEvent.click(screen.getByTestId("comment-lasso-erase-label"));
    }
    expect(marks()).toHaveLength(0);
    expect(screen.queryByTestId("comment-lasso-note")).toBeNull();
    expect(screen.queryByTestId("comment-lasso-leader")).toBeNull();
  });

  it("keys 1 to 4 change the next mark's pen and retain previous ink", async () => {
    await mount();
    const colors = ["rgb(139, 92, 246)", "rgb(220, 38, 38)", "rgb(234, 88, 12)", "rgb(202, 138, 4)"];
    colors.forEach((color, i) => {
      fireEvent.keyDown(window, { key: String(i + 1) });
      draw([[400, 100 + i * 40], [430, 105 + i * 40], [460, 100 + i * 40]]);
      expect(marks().map((mark) => mark.getAttribute("stroke"))).toEqual(colors.slice(0, i + 1));
      expect(marks()[i]!.getAttribute("stroke")).toBe(color);
    });
  });

  it("New gives a fresh ground and a tap on the old ground restores its stack", async () => {
    await mount(); draw(ring); label("First remark");
    const ground = screen.getByTestId("comment-lasso-blob").getAttribute("fill");
    fireEvent.click(screen.getByTestId("comment-lasso-new"));
    expect(screen.getByTestId("comment-lasso-shelved")).toBeTruthy();
    draw(ring.map(([x, y]) => [x + 350, y + 200])); label("Second remark");
    expect(screen.getByTestId("comment-lasso-blob").getAttribute("fill")).not.toBe(ground);
    const surface = screen.getByTestId("comment-lasso-surface");
    fireEvent.pointerDown(surface, { clientX: 150, clientY: 140, button: 0 });
    fireEvent.pointerUp(surface, { clientX: 150, clientY: 140, button: 0 });
    await waitFor(() => expect((screen.getByTestId("comment-lasso-note") as HTMLTextAreaElement).value).toBe("First remark"));
    expect((screen.getByTestId("comment-lasso-note") as HTMLTextAreaElement).value).toBe("First remark");
    expect(screen.getByTestId("comment-lasso-blob").getAttribute("fill")).toBe(ground);
    expect(screen.getAllByTestId("comment-lasso-shelved")).toHaveLength(1);
  });

  it("keeps live ink, labels and shelved stacks while the pen is inactive", async () => {
    const { setActive } = await mount();
    draw(ring); label("First remark");
    fireEvent.click(screen.getByTestId("comment-lasso-new"));
    draw(ring.map(([x, y]) => [x + 350, y + 200])); label("Second remark");
    const livePoints = marks().at(-1)!.getAttribute("points");
    const ground = screen.getByTestId("comment-lasso-blob").getAttribute("fill");
    await setActive(false);
    expect(screen.queryByTestId("comment-lasso-surface")).toBeNull();
    await setActive(true);
    expect(marks().at(-1)!.getAttribute("points")).toBe(livePoints);
    expect((screen.getByTestId("comment-lasso-note") as HTMLTextAreaElement).value).toBe("Second remark");
    expect(screen.getByTestId("comment-lasso-blob").getAttribute("fill")).toBe(ground);
    expect(screen.getAllByTestId("comment-lasso-shelved")).toHaveLength(1);
    const surface = screen.getByTestId("comment-lasso-surface");
    fireEvent.pointerDown(surface, { clientX: 150, clientY: 140, button: 0 });
    fireEvent.pointerUp(surface, { clientX: 150, clientY: 140, button: 0 });
    await waitFor(() => expect((screen.getByTestId("comment-lasso-note") as HTMLTextAreaElement).value).toBe("First remark"));
  });

  it("gives independently mounted overlays their own ink lifetime", async () => {
    const first = await mount();
    const second = await mount();
    const surface = first.container.querySelector<HTMLElement>('[data-testid="comment-lasso-surface"]')!;
    draw(ring, surface);
    const note = first.container.querySelector<HTMLTextAreaElement>('[data-testid="comment-lasso-note"]')!;
    fireEvent.change(note, { target: { value: "Only the first overlay" } });
    fireEvent.keyDown(note, { key: "Enter" });
    expect(first.container.querySelector("polyline")).toBeTruthy();
    expect(second.container.querySelector("polyline")).toBeNull();
    expect(second.container.querySelector('[data-testid="comment-lasso-note"]')).toBeNull();
    second.unmount();
    expect(first.container.querySelector("polyline")).toBeTruthy();
    expect(note.value).toBe("Only the first overlay");
  });

  it("holding Space lifts every overlay and releases the pointer to the node underneath", async () => {
    const { underHover } = await mount(); draw(ring); label();
    fireEvent.keyDown(window, { key: " ", code: "Space" });
    const surface = screen.getByTestId("comment-lasso-surface");
    expect(surface.classList.contains("pointer-events-none")).toBe(true);
    expect(surface.parentElement!.hasAttribute("data-pen-up")).toBe(true);
    expect(document.body.hasAttribute("data-pen-lifted")).toBe(true);
    fireEvent.mouseEnter(screen.getByTestId("underlying-node"));
    expect(underHover).toHaveBeenCalledOnce();
    fireEvent.keyUp(window, { key: " ", code: "Space" });
    expect(surface.classList.contains("pointer-events-none")).toBe(false);
    expect(surface.parentElement!.hasAttribute("data-pen-up")).toBe(false);
    expect(marks()).toHaveLength(1);
  });

  it("sends the drawing, words and target once, then keeps the ink as a ghost", async () => {
    const { onFiled } = await mount(); draw(ring); label("Check this value");
    fireEvent.click(screen.getByTestId("comment-lasso-send"));
    await waitFor(() => expect(screen.getByTestId("comment-lasso-ghost")).toBeTruthy());
    expect(intents.create).toHaveBeenCalledOnce();
    expect(intents.create).toHaveBeenCalledWith(expect.objectContaining({ workspaceSlug: "study",
      targets: ["pump"], text: expect.stringContaining("Check this value"),
      sketch: expect.objectContaining({ nodes: expect.arrayContaining([expect.objectContaining({ encircles: "pump" })]) }),
    }));
    expect(screen.queryByTestId("comment-lasso-note")).toBeNull();
    expect(screen.getByTestId("comment-lasso-ghost").querySelector("polyline")).toBeTruthy();
    expect(onFiled).toHaveBeenCalledOnce();
  });

  it.each(["pending", "applied"])("renders a suggestion in %s state from a thread", async (state) => {
    const intent = baseIntent();
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Use the new limit", created_at: 2, state,
      ops: [{ type: "NodeUpdated", payload: { id: "pump", fields: { label: "Pump limit" } } }] }];
    vi.mocked(intents.listPending).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    const card = await screen.findByTestId(state === "pending" ? "comment-lasso-ghost-verdict" : "comment-lasso-ghost-applied");
    expect(card.textContent).toContain("Use the new limit");
    expect(card.textContent).toContain(state === "pending" ? "proposal" : "done");
  });

  it("reads a two-stroke cross as a strike, leaving a lone crossing as ordinary ink", async () => {
    useCanvasStore.setState({ edges: { link: { id: "link", source: "pump", target: "motor", label: "", edge_type: "floating" } } });
    const edge = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    edge.setAttribute("class", "react-flow__edge"); edge.setAttribute("data-id", "link");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", "react-flow__edge-path");
    Object.assign(path, { getTotalLength: () => 200, getScreenCTM: () => ({}),
      getPointAtLength: (length: number) => ({ matrixTransform: () => ({ x: 400 + length, y: 400 }) }) });
    edge.append(path); document.body.append(edge);
    try {
      await mount();
      draw([[470, 370], [500, 400], [530, 430]]);
      expect(screen.queryByTestId("comment-lasso-strikes")).toBeNull();
      draw([[530, 370], [500, 400], [470, 430]]);
      expect(screen.getByTestId("comment-lasso-strikes").textContent).toContain("link");
      fireEvent.click(screen.getByTestId("comment-lasso-send"));
      await waitFor(() => expect(intents.create).toHaveBeenCalledOnce());
      expect(intents.create).toHaveBeenCalledWith(expect.objectContaining({
        targets: ["pump", "motor"],
        strikes: [expect.objectContaining({ edge: "link", source: "pump", target: "motor" })],
      }));
    } finally { edge.remove(); }
  });

  it("renders question options and posts the selected answer", async () => {
    const intent = baseIntent();
    intent.items = [{ id: "question", type: "question", author: { kind: "agent" },
      text: "Which limit?", options: ["Nominal", "Maximum"], created_at: 2, state: "open" }];
    vi.mocked(intents.listPending).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    await screen.findByTestId("comment-lasso-ghost-question");
    expect(screen.getAllByTestId("comment-lasso-option")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Maximum" }));
    expect(intents.answer).toHaveBeenCalledWith("ask", "question", "Maximum");
  });
});
