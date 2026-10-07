// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import type { Intent, ThreadItem } from "@/api/intents";
import { createMarkupStore, GHOST_GROUNDS, PALETTE, type Mark, type Queued } from "./markupStore";

const mark = (color: string = PALETTE[0].ink): Mark => ({
  color, points: [{ x: 0, y: 0 }, { x: 100, y: 100 }],
});
const intent = (id = "intent-1", items: ThreadItem[] = []): Intent => ({
  id, kind: "user_request", origin_canvas_id: "canvas-a", target: null,
  payload: { text: "Check this" }, status: "pending", created_at: 1, items,
});
const suggestion = (id: string, state: string): ThreadItem => ({
  id, type: "suggestion", state, text: "Change", author: { kind: "agent" }, created_at: 1,
});
function live(store: ReturnType<typeof createMarkupStore>, id = "stack-1"): Queued {
  const state = store.getState();
  return { id, text: state.notes.map((note) => note.text).join("\n"), ids: state.ids,
    marks: state.marks, notes: state.notes, sketch: { nodes: [], edges: [] }, cuts: [], strikes: [] };
}
function draw(store: ReturnType<typeof createMarkupStore>, text = "Check this") {
  store.getState().addMark(mark(store.getState().ink));
  store.getState().updateNotes([{ id: "note", x: 20, y: 30, text, inStroke: 0 }]);
  store.getState().setTargets(["node-a"]);
}

describe("markup actions without a DOM", () => {
  it("keeps durable records while pausing and starts each overlay with its own lifetime", () => {
    const first = createMarkupStore();
    draw(first);
    first.getState().newStack(live(first));
    draw(first, "Another ask");
    first.getState().openThread("thread-a");
    first.getState().keepSuggestion("judged");
    first.getState().selectMarks({ strokes: [0], notes: [] });
    first.getState().editNote("note");
    first.getState().liftPen(true);
    const before = first.getState();
    first.getState().pauseMarkup();
    const paused = first.getState();
    for (const field of ["marks", "notes", "ink", "shelf", "ground", "groundSeq", "openFiled", "kept"] as const) {
      expect(paused[field]).toBe(before[field]);
    }
    expect(paused.selected).toEqual({ strokes: [], notes: [] });
    expect(paused.editing).toBeNull();
    expect(paused.lifted).toBe(false);
    const second = createMarkupStore();
    expect(second.getState().marks).toEqual([]);
    expect(second.getState().shelf).toEqual([]);
    expect(second.getState().kept.size).toBe(0);
    expect(second.getState().openFiled).toBeNull();
    draw(second);
    second.getState().resetRemark();
    expect(first.getState().marks).toHaveLength(1);
    expect(createMarkupStore().getState().groundSeq).toBe(0);
  });

  it.each(["ring", "leader", "label"])("deleting a linked %s closes the gesture and reindexes survivors", (part) => {
    const store = createMarkupStore();
    store.getState().replaceMarks([mark(), mark(), mark(), mark()]);
    store.getState().updateNotes([
      { id: "linked", x: 0, y: 0, text: "Ring", ringStroke: 0, onStroke: 1 },
      { id: "inside", x: 0, y: 0, text: "Inside", inStroke: 0 },
      { id: "survivor", x: 1, y: 2, text: "Keep", inStroke: 2, onStroke: 3, ringStroke: 2 },
    ]);
    store.getState().setManualTargets(["manual-node"]);
    store.getState().selectLabel("linked");
    store.getState().hoverMark(1);
    const observed: number[] = [];
    store.subscribe((state) => observed.push(state.marks.length));
    store.getState().dropMarks(part === "label" ? [] : [part === "ring" ? 0 : 1], part === "label" ? ["linked"] : [], []);
    expect(store.getState().marks).toHaveLength(2);
    expect(store.getState().notes).toEqual([
      { id: "survivor", x: 1, y: 2, text: "Keep", inStroke: 0, onStroke: 1, ringStroke: 0 },
    ]);
    expect(store.getState().ids).toEqual(["manual-node"]);
    expect(store.getState().activeLabel).toBeNull();
    expect(store.getState().hoveredStroke).toBeNull();
    expect(observed).toEqual([2]);
  });

  it("recolours picked marks and their hosted words while retaining unrelated ink", () => {
    const store = createMarkupStore();
    store.getState().replaceMarks([mark(), mark()]);
    store.getState().updateNotes([
      { id: "hosted", x: 0, y: 0, text: "Host", inStroke: 0 },
      { id: "picked", x: 1, y: 1, text: "Picked" },
      { id: "untouched", x: 2, y: 2, text: "Keep", color: PALETTE[0].ink },
    ]);
    store.getState().selectMarks({ strokes: [0], notes: ["picked"] });
    store.getState().recolour(PALETTE[1].ink);
    expect(store.getState().ink).toBe(PALETTE[1].ink);
    expect(store.getState().marks.map((mark) => mark.color)).toEqual([PALETTE[1].ink, PALETTE[0].ink]);
    expect(store.getState().notes.map((note) => note.color)).toEqual([PALETTE[1].ink, PALETTE[1].ink, PALETTE[0].ink]);
  });

  it("commits words and drops only empty notes while leaving other editing alone", () => {
    const store = createMarkupStore();
    store.getState().updateNotes([
      { id: "empty", x: 0, y: 0, text: " " },
      { id: "written", x: 0, y: 0, text: "Keep" },
    ]);
    store.getState().editNote("written");
    store.getState().commitNote("empty");
    expect(store.getState().notes.map((note) => note.id)).toEqual(["written"]);
    expect(store.getState().editing).toBe("written");
    store.getState().commitNote("written");
    expect(store.getState().editing).toBeNull();
    expect(store.getState().notes[0]?.text).toBe("Keep");
  });

  it("shelves and restores full snapshots atomically without rotating the restored ground", () => {
    const store = createMarkupStore();
    draw(store);
    const snapshot = live(store, "first");
    snapshot.notes = [{ ...snapshot.notes[0]!, x: 200, y: 300, offered: true }];
    store.getState().newStack(snapshot);
    expect(store.getState().ground).toBe(GHOST_GROUNDS[1]);
    expect(store.getState().groundSeq).toBe(1);
    expect(store.getState().ink).toBe(PALETTE[1].ink);
    expect(store.getState().marks).toEqual([]);
    draw(store, "Second");
    const observed: string[][] = [];
    store.subscribe((state) => observed.push(state.notes.map((note) => note.text)));
    store.getState().switchStack("first", live(store, "second"));
    expect(observed).toEqual([["Check this"]]);
    expect(store.getState().notes[0]).toMatchObject({ x: 200, y: 300, offered: false });
    expect(store.getState().shelf.map((stack) => stack.id)).toEqual(["second"]);
    expect(store.getState().manual).toEqual(["node-a"]);
    expect(store.getState().ground).toBe(GHOST_GROUNDS[0]);
    expect(store.getState().groundSeq).toBe(1);
    expect(store.getState().ink).toBe(PALETTE[0].ink);
    const before = store.getState();
    store.getState().switchStack("absent", live(store));
    expect(store.getState().marks).toBe(before.marks);
  });

  it("ignores New with no remark", () => {
    const store = createMarkupStore();
    store.getState().newStack(live(store));
    expect(store.getState().shelf).toEqual([]);
    expect(store.getState().groundSeq).toBe(0);
    expect(store.getState().ink).toBe(PALETTE[0].ink);
  });

  it("guards duplicate sends and archives exactly the captured remark on success", async () => {
    const store = createMarkupStore();
    draw(store);
    const snapshot = live(store);
    let complete!: (intent: Intent) => void;
    const create = vi.fn(() => new Promise<Intent>((resolve) => { complete = resolve; }));
    const pending = store.getState().send(snapshot, create);
    expect(store.getState().sending).toBe(true);
    expect(await store.getState().send(snapshot, create)).toBe(false);
    expect(create).toHaveBeenCalledTimes(1);
    complete(intent());
    expect(await pending).toBe(true);
    expect(store.getState().sending).toBe(false);
    expect(store.getState().marks).toEqual([]);
    expect(store.getState().filed[0]).toMatchObject({ marks: snapshot.marks, notes: snapshot.notes, ground: GHOST_GROUNDS[0] });
    expect(store.getState().groundSeq).toBe(1);
  });

  it("leaves unsent ink and its ground intact after an API failure", async () => {
    const store = createMarkupStore();
    draw(store);
    const before = store.getState();
    await expect(store.getState().send(live(store), () => Promise.reject(new Error("offline")))).rejects.toThrow("offline");
    expect(store.getState().sending).toBe(false);
    expect(store.getState().marks).toBe(before.marks);
    expect(store.getState().notes).toBe(before.notes);
    expect(store.getState().ground).toBe(before.ground);
    expect(store.getState().groundSeq).toBe(0);
    expect(store.getState().filed).toEqual([]);
  });

  it("merges ghosts by intent id and removes resolved ghosts only when no pending proposal remains", () => {
    const store = createMarkupStore();
    draw(store);
    const queued = live(store);
    const ghost = { intentId: "one", text: queued.text, ids: queued.ids, sketch: queued.sketch,
      marks: queued.marks, notes: queued.notes, color: PALETTE[0].ink, intent: intent("one") };
    store.getState().loadFiled([ghost]);
    store.getState().loadFiled([{ ...ghost, text: "Duplicate" }, { ...ghost, intentId: "two", intent: intent("two") }]);
    expect(store.getState().filed.map((ghost) => ghost.text)).toEqual([queued.text, queued.text]);
    store.getState().openThread("one");
    store.getState().refreshFiled([
      { ...intent("one", [suggestion("s1", "pending")]), status: "resolved" },
      { ...intent("two", [suggestion("s2", "applied")]), status: "resolved" },
    ]);
    expect(store.getState().filed.map((ghost) => ghost.intentId)).toEqual(["one"]);
    expect(store.getState().openFiled).toBe("one");
  });

  it("settles only after all pending and unjudged applied suggestions are gone", async () => {
    const store = createMarkupStore();
    const host = { get: vi.fn(async () => intent("one", [suggestion("s", "applied")])), resolve: vi.fn(async () => undefined) };
    await store.getState().settle("one", new Set(), host);
    expect(host.resolve).not.toHaveBeenCalled();
    const judged = store.getState().keepSuggestion("s");
    await store.getState().settle("one", judged, host);
    expect(host.resolve).toHaveBeenCalledWith("one", { verdict: "judged on the board" });
    host.get.mockResolvedValue(intent("one", [suggestion("s", "pending")]));
    host.resolve.mockClear();
    await store.getState().settle("one", judged, host);
    expect(host.resolve).not.toHaveBeenCalled();
  });
});
