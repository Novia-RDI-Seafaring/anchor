import { describe, expect, it } from "vitest";
import { captureCanvas, planCanvasPaste, type ClipboardNode, type ClipboardEdge } from "./clipboard";

const node = (id: string, parent: string | null = null): ClipboardNode => ({ id, parent, node_type: "concept", label: id, x: 100, y: 200 });
const edge: ClipboardEdge = { id: "join", source: "child", target: "sibling", label: "linked", edge_type: "anchored", sourceHandle: "row:flow", targetHandle: "in:flow" };
const freshIds = () => { let i = 0; return () => `new-${++i}`; };

describe("canvas clipboard", () => {
  it("copies nested contents before children and remaps their internal connectors", () => {
    const nodes = { child: node("child", "nested"), sibling: node("sibling", "area"), nested: node("nested", "area"), area: node("area") };
    const copy = captureCanvas({ nodes, edges: { join: edge } }, "a", ["area"]);
    expect(copy.nodes.map((n) => n.id)).toEqual(["area", "sibling", "nested", "child"]);
    const pasted = planCanvasPaste(copy, "b", new Set(), { x: 24, y: 48 }, freshIds());
    const child = pasted.nodes.find((n) => n.label === "child")!;
    expect(child).toMatchObject({ id: "new-4", parent: "new-3", x: 124, y: 248 });
    expect(pasted.edges[0]).toMatchObject({ id: "new-5", source: child.id, target: "new-2", sourceHandle: "row:flow", targetHandle: "in:flow" });
    expect(nodes.child.x).toBe(100);
  });

  it("preserves source refs and values while clearing inherited human review and evidence", () => {
    const source_ref = { slug: "pump", page: 2, bbox: [1, 2, 3, 4], detail: { quote: "42 bar" } };
    const original = { ...node("spec"), data: { review: { verdict: "approved" }, rows: [{ key: "p", value: 42, source_ref,
      review: { verdict: "reject" }, evidence: { state: "verified" }, revalidate_evidence: true }] } };
    const copy = captureCanvas({ nodes: { spec: original }, edges: {} }, "a", ["spec"]);
    const pasted = planCanvasPaste(copy, "a", new Set(["spec"]), { x: 0, y: 0 }, freshIds());
    expect(pasted.nodes[0]!.data).toEqual({ rows: [{ key: "p", value: 42, source_ref }] });
    expect(original.data.review).toEqual({ verdict: "approved" });
    expect(pasted.nodes[0]!.data).not.toBe(original.data);
  });

  it("keeps an existing external parent on the same canvas and detaches it across canvases", () => {
    const fragment = captureCanvas({ nodes: { child: node("child", "area") }, edges: {} }, "a", ["child"]);
    expect(planCanvasPaste(fragment, "a", new Set(["area"]), { x: 0, y: 0 }, freshIds()).nodes[0]!.parent).toBe("area");
    expect(planCanvasPaste(fragment, "b", new Set(["area"]), { x: 0, y: 0 }, freshIds()).nodes[0]!.parent).toBeNull();
  });

  it("copies selected connectors alone locally but requires endpoints across canvases", () => {
    const fragment = captureCanvas({ nodes: {}, edges: { join: edge } }, "a", [], ["join"]);
    expect(planCanvasPaste(fragment, "a", new Set(["child", "sibling"]), { x: 0, y: 0 }, freshIds()).edges[0]!.source).toBe("child");
    expect(() => planCanvasPaste(fragment, "b", new Set(["child", "sibling"]), { x: 0, y: 0 }, freshIds())).toThrow("both endpoints");
  });
});
