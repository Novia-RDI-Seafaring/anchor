import { describe, expect, it } from "vitest";

import schema from "@/generated/anchor-core.schema.json";
import { CANVAS_EDGE_WIRE_FIELDS, CANVAS_NODE_WIRE_FIELDS } from "@/stores/canvasStore";

describe("anchor core wire schema snapshot", () => {
  it("matches the canvas store node and edge fields", () => {
    expect(schema.models.Node.fields).toEqual([...CANVAS_NODE_WIRE_FIELDS]);
    expect(schema.models.Edge.fields).toEqual([...CANVAS_EDGE_WIRE_FIELDS]);
  });
});
