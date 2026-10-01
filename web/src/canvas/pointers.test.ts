import { describe, expect, it } from "vitest";

import { describePointers, resolvePointers } from "@/canvas/pointers";

const card = { id: "dims", x: 100, y: 100, width: 300, height: 250 };
const region = { id: "zone", x: 0, y: 0, width: 1000, height: 1000 };
const rows = [
  { key: "A", top: 170, bottom: 210 },
  { key: "B", top: 210, bottom: 250 },
  { key: "C", top: 250, bottom: 290 },
];
const rowsOf = (id: string) => (id === "dims" ? rows : null);

describe("resolvePointers", () => {
  it("names the row a label's line starts in", () => {
    const line = [{ x: 220, y: 190 }, { x: 500, y: 60 }];
    const got = resolvePointers([{ text: "add +1", x: 520, y: 50, onStroke: 0 }], [line], [card], rowsOf);
    expect(got).toEqual([{ text: "add +1", node: "dims", row: "A", rowIndex: 0, at: { x: 220, y: 190 } }]);
  });

  it("takes the end away from the words, whichever way the line was drawn", () => {
    const line = [{ x: 500, y: 60 }, { x: 220, y: 230 }];
    const got = resolvePointers([{ text: "this one", x: 520, y: 50, onStroke: 0 }], [line], [card], rowsOf);
    expect(got[0]?.row).toBe("B");
  });

  it("uses the leader's start when the note has no line of its own", () => {
    const got = resolvePointers([{ text: "why?", x: 600, y: 300, from: { x: 200, y: 270 } }], [], [card], rowsOf);
    expect(got[0]).toMatchObject({ node: "dims", row: "C" });
  });

  it("names the smallest card under the start", () => {
    const got = resolvePointers([{ text: "x", x: 600, y: 300, from: { x: 200, y: 180 } }], [], [region, card], rowsOf);
    expect(got[0]?.node).toBe("dims");
  });

  it("names the card alone when the start is not in a row", () => {
    const got = resolvePointers([{ text: "rename", x: 600, y: 300, from: { x: 200, y: 120 } }], [], [card], rowsOf);
    expect(got[0]).toEqual({ text: "rename", node: "dims", at: { x: 200, y: 120 } });
  });

  it("leaves out a ring's label, and a line that starts on empty canvas", () => {
    const got = resolvePointers(
      [
        { text: "ringed", x: 600, y: 300, from: { x: 200, y: 180 }, ringStroke: 0 },
        { text: "loose", x: 600, y: 300, from: { x: 900, y: 1200 } },
        { text: "   ", x: 600, y: 300, from: { x: 200, y: 180 } },
      ],
      [],
      [card],
      rowsOf,
    );
    expect(got).toEqual([]);
  });
});

describe("describePointers", () => {
  it("reads as a sentence an agent can act on", () => {
    expect(
      describePointers([
        { text: "add +1", node: "dims", row: "A", rowIndex: 0, at: { x: 0, y: 0 } },
        { text: "rename", node: "lkh5", at: { x: 0, y: 0 } },
      ]),
    ).toBe('"add +1" drawn from row A of dims; "rename" drawn from lkh5');
  });
});
