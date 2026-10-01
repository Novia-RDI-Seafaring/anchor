/**
 * What a proposal changed — structurally, so the highlight can land on the
 * cell that moved rather than on the whole card.
 */
import { describe, expect, it } from "vitest";

import { changeCount, diffNodeData, diffRows, onlyGeometry } from "@/canvas/nodeDiff";

describe("diffNodeData", () => {
  it("reports the field that changed and what it was", () => {
    const d = diffNodeData({ label: "Original" }, { label: "Cap'n Card" });
    expect(d.fields).toEqual([{ field: "label", before: "Original", after: "Cap'n Card" }]);
    expect(d.unchanged).toBe(false);
  });

  it("says nothing changed when nothing did", () => {
    expect(diffNodeData({ label: "same" }, { label: "same" }).unchanged).toBe(true);
  });

  it("ignores fields the proposal never captured", () => {
    // `before` holds only what was touched. Treating every absent field as a
    // change would paint the whole card as edited.
    const d = diffNodeData({ label: "a" }, { label: "a", description: "added later" });
    expect(d.unchanged).toBe(true);
  });

  it("compares nested values properly rather than by identity", () => {
    const d = diffNodeData(
      { source_ref: { page: 3, cell: { row: 1, col: 2 } } },
      { source_ref: { page: 3, cell: { row: 1, col: 2 } } },
    );
    expect(d.unchanged).toBe(true);
  });
});

describe("diffRows", () => {
  const row = (key: string, value: string) => ({ key, value });

  it("names which field of a row changed", () => {
    const d = diffRows([row("Width", "")], [row("Width", "320 (invented)")]);
    expect(d).toHaveLength(1);
    expect(d[0]).toMatchObject({ index: 0, kind: "changed", fields: ["value"] });
  });

  it("spots an added and a removed row", () => {
    expect(diffRows([row("A", "1")], [row("A", "1"), row("B", "2")])[0]).toMatchObject({
      index: 1, kind: "added",
    });
    expect(diffRows([row("A", "1"), row("B", "2")], [row("A", "1")])[0]).toMatchObject({
      index: 1, kind: "removed",
    });
  });

  it("notices a reference changing even when the value did not", () => {
    // The number is right and the citation moved: the state most worth seeing.
    const d = diffRows(
      [{ key: "B", value: "87", source_ref: { page: 3, region_id: "r2" } }],
      [{ key: "B", value: "87", source_ref: { page: 3, region_id: "r5" } }],
    );
    expect(d[0]!.fields).toEqual(["source_ref"]);
  });

  it("leaves rows alone when the proposal did not capture them", () => {
    expect(diffRows(undefined, [row("A", "1")])).toEqual([]);
  });

  it("reports unchanged rows as nothing at all", () => {
    expect(diffRows([row("A", "1")], [row("A", "1")])).toEqual([]);
  });
});

describe("choosing how to show it", () => {
  it("counts each changed thing, so one value can read inline", () => {
    expect(changeCount(diffNodeData({ label: "a" }, { label: "b" }))).toBe(1);
    expect(
      changeCount(
        diffNodeData(
          { label: "a", rows: [{ key: "W", value: "" }] },
          { label: "b", rows: [{ key: "W", value: "320" }] },
        ),
      ),
    ).toBe(2);
  });

  it("knows when a change is only about where the card sits", () => {
    // Side by side, both panes look identical; that wants a ghost on the
    // canvas instead of a panel.
    expect(onlyGeometry(diffNodeData({ x: 0, y: 0 }, { x: 40, y: 90 }))).toBe(true);
    expect(onlyGeometry(diffNodeData({ x: 0, label: "a" }, { x: 40, label: "b" }))).toBe(false);
  });
});
