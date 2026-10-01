/**
 * A hovered reference lit on a picture of its page. The failure this guards
 * against: the drawing on the canvas staying dark while the source lights up.
 */
import { describe, expect, it } from "vitest";

import { boxesOnPicture, isOwnHover, placesFromAlso } from "@/canvas/sourceHighlight";

// The dimension drawing, cut from page 3.
const crop = { page: 3, bbox: [56, 58, 291, 189] };

describe("lighting a reference on a picture of its page", () => {
  it("maps a letter's box into the picture, in percent", () => {
    const [box] = boxesOnPicture(crop, [{ page: 3, bbox: [251.2, 85.1, 256.2, 92.1] }]);
    expect(box!.left).toBeCloseTo(((251.2 - 56) / 235) * 100, 5);
    expect(box!.top).toBeCloseTo(((85.1 - 58) / 131) * 100, 5);
    expect(box!.width).toBeCloseTo((5 / 235) * 100, 5);
  });

  it("drops what is outside the cut or on another page", () => {
    expect(boxesOnPicture(crop, [{ page: 3, bbox: [300, 400, 320, 410] }])).toEqual([]);
    expect(boxesOnPicture(crop, [{ page: 2, bbox: [251, 85, 256, 92] }])).toEqual([]);
  });

  it("reads the places an also list names, skipping ones with no box", () => {
    expect(
      placesFromAlso([
        { slug: "lkh", page: 3, bbox: [251.2, 85.1, 256.2, 92.1] },
        "p3/r1/item:p3-i6",
        { page: 3 },
      ]),
    ).toEqual([{ page: 3, bbox: [251.2, 85.1, 256.2, 92.1] }]);
  });
});

describe("isOwnHover", () => {
  const cut = { region_id: "r3", bbox: [110, 405, 490, 730] };
  it("is the picture's own hover when the region is the whole of it", () => {
    expect(isOwnHover(cut, { region_id: "r3" })).toBe(true);
    expect(isOwnHover(cut, { region_id: "r3", bbox: [110, 405, 490, 730] })).toBe(true);
  });
  it("is not when a row points at one label inside the same region", () => {
    expect(isOwnHover(cut, { region_id: "r3", bbox: [272, 410, 322, 428] })).toBe(false);
  });
  it("is not for a cell, an item, extra places or another region", () => {
    expect(isOwnHover(cut, { region_id: "r3", cell: { row: 1, col: 1 } })).toBe(false);
    expect(isOwnHover(cut, { region_id: "r3", item_id: "p2-i4" })).toBe(false);
    expect(isOwnHover(cut, { region_id: "r3", places: [{ page: 2, bbox: [1, 2, 3, 4] }] })).toBe(false);
    expect(isOwnHover(cut, { region_id: "r1" })).toBe(false);
  });
});
