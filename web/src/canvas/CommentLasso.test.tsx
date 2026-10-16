import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { intents, type Intent, type ThreadItem } from "@/api/intents";
import { useCanvasStore } from "@/stores/canvasStore";
import { CommentLasso } from "./CommentLasso";

const flow = vi.hoisted(() => ({
  viewport: { x: 0, y: 0, zoom: 1 },
  getViewport: vi.fn(), setViewport: vi.fn(), fitBounds: vi.fn(), screenToFlowPosition: vi.fn(),
}));
vi.mock("@xyflow/react", () => ({
  useReactFlow: () => flow,
  useViewport: () => flow.viewport,
  useStoreApi: () => ({ getState: () => ({ width: 1000, height: 800 }) }),
}));
vi.mock("@/api/intents", () => ({
  INTENTS_CHANGED_EVENT: "anchor:intents-changed",
  intents: { listAll: vi.fn(), get: vi.fn(), create: vi.fn(), answer: vi.fn(),
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
  vi.mocked(intents.listAll).mockResolvedValue([]);
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
  const onEnter = vi.fn();
  const underHover = vi.fn();
  const view = (active: boolean) => <div className="react-flow">
    <button data-testid="underlying-node" onMouseEnter={underHover}>Pump</button>
    <CommentLasso active={active} boxes={boxes} workspaceSlug="study" onExit={onExit} onEnter={onEnter} onFiled={onFiled} />
  </div>;
  const result = render(view(true));
  const setActive = async (active: boolean) => { await act(async () => { result.rerender(view(active)); }); };
  await act(async () => {});
  return { ...result, onExit, onEnter, onFiled, underHover, setActive };
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
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    const card = await screen.findByTestId(state === "pending" ? "comment-lasso-ghost-verdict" : "comment-lasso-ghost-applied");
    expect(card.textContent).toContain("Use the new limit");
    expect(card.textContent).toContain(state === "pending" ? "proposal" : "done");
  });

  it("still asks to keep a change the agent applied and then resolved, and records the keep", async () => {
    const intent = { ...baseIntent(), status: "resolved", result: { built: "Org chart" } };
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Added the org chart", created_at: 2, state: "applied",
      ops: [{ type: "NodeUpdated", payload: { id: "pump", fields: { label: "Pump limit" } } }] }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    await screen.findByTestId("comment-lasso-ghost-applied");
    fireEvent.click(screen.getByTestId("comment-lasso-keep"));
    await waitFor(() => expect(intents.resolve).toHaveBeenCalledWith("ask", {
      built: "Org chart", verdict: "judged on the board", kept: ["change"],
    }));
  });

  it("marks the real cards a change touched until the reader keeps it", async () => {
    const intent = baseIntent();
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Renamed the pump", created_at: 2, state: "applied",
      ops: [{ type: "NodeUpdated", payload: { id: "pump", fields: { label: "Pump limit" } } }],
      undo_ops: [{ type: "NodeUpdated", payload: { id: "pump", fields: { label: "Old pump" } } }] }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    await screen.findByTestId("comment-lasso-ghost-applied");
    const css = () => document.getElementById("anchor-change-marks")?.textContent ?? "";
    await waitFor(() => expect(css()).toContain('.react-flow__node[data-id="pump"]'));
    expect(css()).toContain('content: "Old pump"');
    fireEvent.pointerEnter(screen.getByTestId("comment-lasso-ghost-applied"));
    await waitFor(() => expect(css()).toContain("box-shadow"));
    fireEvent.click(screen.getByTestId("comment-lasso-keep"));
    await waitFor(() => expect(document.getElementById("anchor-change-marks")).toBeNull());
  });

  it("leaves intent mode once the last open remark is kept", async () => {
    const intent = baseIntent();
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Renamed the pump", created_at: 2, state: "applied", ops: [] }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    const { onExit } = await mount();
    fireEvent.click(await screen.findByTestId("comment-lasso-keep"));
    await waitFor(() => expect(intents.resolve).toHaveBeenCalled());
    await waitFor(() => expect(onExit).toHaveBeenCalledOnce());
  });

  it("stays in intent mode while another remark is still open", async () => {
    const judged = baseIntent();
    judged.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Renamed the pump", created_at: 2, state: "applied", ops: [] }];
    const other = { ...baseIntent(), id: "other", items: [] };
    vi.mocked(intents.listAll).mockResolvedValue([judged, other]);
    vi.mocked(intents.get).mockImplementation(async (id) => (id === "other" ? other : judged));
    const { onExit } = await mount();
    fireEvent.click(await screen.findByTestId("comment-lasso-keep"));
    await waitFor(() => expect(intents.resolve).toHaveBeenCalled());
    await act(async () => {});
    expect(onExit).not.toHaveBeenCalled();
  });

  it("takes a reader with the pen down back to the remark when the agent answers", async () => {
    const asked = { ...baseIntent(), payload: { text: "Check the pump", viewport: { x: -40, y: -20, zoom: 1.5 } } };
    const answered = { ...asked, items: [{ id: "change", type: "suggestion" as const, author: { kind: "agent", label: "claude-code" },
      text: "Renamed the pump", created_at: 2, state: "applied", ops: [] }] };
    vi.mocked(intents.listAll).mockResolvedValue([asked]);
    vi.mocked(intents.get).mockResolvedValue(asked);
    const { onEnter, setActive } = await mount();
    await waitFor(() => expect(intents.get).toHaveBeenCalled());
    await setActive(false);
    vi.mocked(intents.get).mockResolvedValue(answered);
    await act(async () => { window.dispatchEvent(new Event("anchor:intents-changed")); });
    await waitFor(() => expect(onEnter).toHaveBeenCalledOnce());
    await setActive(true);
    // The pump sits inside the view the remark was sent from, so that view
    // comes back as it was.
    await waitFor(() => expect(flow.setViewport).toHaveBeenCalledWith({ x: -40, y: -20, zoom: 1.5 }, expect.anything()));
    expect(await screen.findByTestId("comment-lasso-keep")).toBeTruthy();
  });

  it("widens the view only as far as a change reaching outside it", async () => {
    const asked = { ...baseIntent(), payload: { text: "Check the pump", viewport: { x: 5000, y: 5000, zoom: 1 } } };
    const answered = { ...asked, items: [{ id: "change", type: "suggestion" as const, author: { kind: "agent" },
      text: "Renamed the pump", created_at: 2, state: "applied", ops: [] }] };
    vi.mocked(intents.listAll).mockResolvedValue([asked]);
    vi.mocked(intents.get).mockResolvedValue(asked);
    const { onEnter, setActive } = await mount();
    await waitFor(() => expect(intents.get).toHaveBeenCalled());
    await setActive(false);
    vi.mocked(intents.get).mockResolvedValue(answered);
    await act(async () => { window.dispatchEvent(new Event("anchor:intents-changed")); });
    await waitFor(() => expect(onEnter).toHaveBeenCalledOnce());
    await setActive(true);
    await waitFor(() => expect(flow.fitBounds).toHaveBeenCalled());
    expect(flow.setViewport).not.toHaveBeenCalledWith({ x: 5000, y: 5000, zoom: 1 }, expect.anything());
  });

  it("does not pull the reader back for an answer that was already waiting", async () => {
    const intent = baseIntent();
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Renamed the pump", created_at: 2, state: "applied", ops: [] }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    const { onEnter, setActive } = await mount();
    await screen.findByTestId("comment-lasso-keep");
    await setActive(false);
    await act(async () => { window.dispatchEvent(new Event("anchor:intents-changed")); });
    await act(async () => {});
    expect(onEnter).not.toHaveBeenCalled();
  });

  it("asks about a revision once, shows what was said, and keeps the change it revised", async () => {
    const intent = baseIntent();
    intent.items = [
      { id: "first", type: "suggestion", author: { kind: "agent", label: "claude-code" },
        text: "Added a joke", created_at: 2, state: "applied", ops: [] },
      { id: "reply", type: "message", author: { kind: "human", label: "browser" },
        text: "make it Markdown", created_at: 3, state: null },
      { id: "second", type: "suggestion", author: { kind: "agent", label: "claude-code" },
        text: "Made it Markdown", created_at: 4, state: "applied", ops: [], supersedes: "first" },
    ];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    const card = await screen.findByTestId("comment-lasso-ghost-applied");
    expect(card.textContent).toContain("Made it Markdown");
    expect(screen.getAllByTestId("comment-lasso-said").map((el) => [el.dataset.author, el.textContent]))
      .toEqual([["human", "make it Markdown"]]);
    expect(screen.getAllByTestId("comment-lasso-keep")).toHaveLength(1);
    fireEvent.click(screen.getByTestId("comment-lasso-keep"));
    await waitFor(() => expect(intents.resolve).toHaveBeenCalledWith("ask", expect.objectContaining({
      kept: expect.arrayContaining(["first", "second"]),
    })));
  });

  it("does not ask to keep a change the reader approved", async () => {
    const intent = baseIntent();
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      applied_by: { kind: "human", label: "browser" },
      text: "Added the tree", created_at: 2, state: "applied", ops: [] }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    await waitFor(() => expect(intents.get).toHaveBeenCalled());
    expect(screen.queryByTestId("comment-lasso-keep")).toBeNull();
  });

  it("leaves a resolved remark off the board once its change was kept", async () => {
    const intent = { ...baseIntent(), status: "resolved",
      result: { verdict: "judged on the board", kept: ["change"] } };
    intent.items = [{ id: "change", type: "suggestion", author: { kind: "agent" },
      text: "Added the org chart", created_at: 2, state: "applied", ops: [] }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    await waitFor(() => expect(intents.listAll).toHaveBeenCalled());
    expect(screen.queryByTestId("comment-lasso-ghost-applied")).toBeNull();
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
        // The ink itself goes too, so a reload redraws the cross as drawn.
        ink: expect.objectContaining({ marks: [expect.anything(), expect.anything()] }),
      }));
    } finally { edge.remove(); }
  });

  it("renders question options and posts the selected answer", async () => {
    const intent = baseIntent();
    intent.items = [{ id: "question", type: "question", author: { kind: "agent" },
      text: "Which limit?", options: ["Nominal", "Maximum"], created_at: 2, state: "open" }];
    vi.mocked(intents.listAll).mockResolvedValue([intent]);
    vi.mocked(intents.get).mockResolvedValue(intent);
    await mount();
    await screen.findByTestId("comment-lasso-ghost-question");
    expect(screen.getAllByTestId("comment-lasso-option")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Maximum" }));
    expect(intents.answer).toHaveBeenCalledWith("ask", "question", "Maximum");
  });
});
