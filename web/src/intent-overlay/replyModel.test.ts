import { describe, expect, it } from "vitest";
import { filedFromIntent } from "./replyModel";
import type { Intent } from "./ports";

const intent = (payload: Record<string, unknown>, targetIds: string[] = []): Intent => ({
  id: "ask", payload, status: "pending", created_at: 1, targetIds, items: [],
});

describe("filedFromIntent", () => {
  it("puts words written on open canvas back where they were written", () => {
    const filed = filedFromIntent(intent({
      text: "add a joke here\n\n--- drawn ---\nwritten on open canvas at 400,300", at: { x: 400, y: 300 },
    }));
    expect(filed?.notes).toEqual([expect.objectContaining({ x: 400, y: 300, text: "add a joke here" })]);
    expect(filed?.ids).toEqual([]);
  });

  it("redraws a remark from its ink, in its own pen, labels included", () => {
    const filed = filedFromIntent(intent({
      text: "make it Norwegian",
      ink: {
        marks: [{ color: "#e11d48", points: [{ x: 0, y: 0 }, { x: 50, y: 40 }] }],
        notes: [{ id: "n1", x: 60, y: 50, text: "make it Norwegian", onStroke: 0, continues: true, color: "#e11d48" }],
      },
    }, ["card"]));
    expect(filed?.color).toBe("#e11d48");
    expect(filed?.marks).toHaveLength(1);
    expect(filed?.notes).toEqual([expect.objectContaining({ text: "make it Norwegian", onStroke: 0, x: 60 })]);
    expect(filed?.ids).toEqual(["card"]);
  });

  it("has nothing to rebuild for a remark with no place and no cards", () => {
    expect(filedFromIntent(intent({ text: "add a joke" }))).toBeNull();
  });
});
