import { describe, expect, it } from "vitest";
import { appendMarkup, captureMarkup, markupSelection } from "./clipboard";
import { createMarkupStore, type Mark, type Note } from "./markupStore";

const marks: Mark[] = [
  { color: "blue", points: [{ x: 0, y: 0 }, { x: 100, y: 100 }], link: { from: "old", to: "target" } },
  { color: "red", points: [{ x: 100, y: 100 }, { x: 200, y: 100 }] },
];
const notes: Note[] = [{ id: "host", x: 10, y: 10, text: "Shape", inStroke: 0 },
  { id: "leader", x: 200, y: 100, text: "Label", onStroke: 1, ringStroke: 0, from: { x: 100, y: 100 } }];

describe("markup clipboard", () => {
  it("copies the full shape/label gesture, remapping indices and fresh note IDs", () => {
    const fragment = captureMarkup({ marks, notes }, { strokes: [], notes: ["leader"] });
    expect(fragment.marks).toHaveLength(2);
    expect(fragment.notes).toHaveLength(2);
    let id = 0;
    const result = appendMarkup({ marks, notes }, fragment, { x: 24, y: 24 }, [], () => `copy-${++id}`);
    expect(result.selected).toEqual({ strokes: [2, 3], notes: ["copy-1", "copy-2"] });
    expect(result.notes[2]).toMatchObject({ id: "copy-1", inStroke: 2, x: 34, y: 34, text: "Shape" });
    expect(result.notes[3]).toMatchObject({ id: "copy-2", onStroke: 3, ringStroke: 2, from: { x: 124, y: 124 } });
    expect(result.marks[2]).not.toHaveProperty("link");
    expect(marks[0]!.points[0]).toEqual({ x: 0, y: 0 });
  });

  it("cuts all connected hosted labels and preserves unrelated ink", () => {
    const store = createMarkupStore();
    store.setState({ marks: [...marks, { color: "green", points: [{ x: 500, y: 500 }] }], notes });
    const selection = markupSelection(store.getState(), { strokes: [], notes: ["host"] });
    const fragment = captureMarkup(store.getState(), selection);
    store.getState().dropMarks(selection.strokes, selection.notes, []);
    expect(store.getState().marks).toHaveLength(1);
    expect(store.getState().notes).toHaveLength(0);
    const pasted = appendMarkup(store.getState(), fragment, { x: 10, y: 20 }, []);
    expect(pasted.notes[0]!.inStroke).toBe(1);
    expect(pasted.notes[1]!.onStroke).toBe(2);
  });
});
