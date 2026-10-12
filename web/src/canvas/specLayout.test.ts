import { describe, expect, it } from "vitest";

import { fitWidth, keyColumnPercent } from "@/canvas/specLayout";

const dims = [{ key: "A", value: "158" }, { key: "B", value: "70" }];
const motors = [
  { key: "LKH-5", value: "IEC80 to IEC90" },
  { key: "LKH-45", value: "IEC100 to IEC180" },
];
const meanings = [{ key: "A - shaft centre up to the outlet face", value: "158" }];

describe("keyColumnPercent", () => {
  it("gives short keys beside long values the smallest share", () => {
    expect(keyColumnPercent(motors)).toBe(27);
    expect(keyColumnPercent(dims)).toBe(25);
  });
  it("gives long keys beside short values the largest share, capped", () => {
    expect(keyColumnPercent(meanings)).toBe(60);
  });
  it("copes with empty rows", () => {
    expect(keyColumnPercent([])).toBe(50);
    expect(keyColumnPercent([{ key: null, value: undefined }])).toBe(50);
  });
});

describe("fitWidth", () => {
  it("fits short rows at the floor", () => {
    expect(fitWidth(dims)).toBe(240);
  });
  it("grows with the longest key and value", () => {
    const w = fitWidth(motors);
    expect(w).toBeGreaterThan(300);
    expect(w).toBeLessThan(400);
    expect(fitWidth(meanings)).toBeGreaterThan(w);
  });
  it("never exceeds the ceiling", () => {
    expect(fitWidth([{ key: "k".repeat(80), value: "v".repeat(80) }])).toBe(760);
  });
  it("scales with the text size", () => {
    expect(fitWidth(motors, 18)).toBeGreaterThan(fitWidth(motors, 14));
  });
});
