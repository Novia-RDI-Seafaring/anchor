import { describe, expect, it } from "vitest";

import fixtures from "./subtree-walk-fixtures.json";
import { cardSummary, foldedGraph, subtreeAdjacency, walkSubtree, type StructureNode, type SubtreeDirection } from "./subtrees";

const node = (id: string, data = {}, node_type = "concept"): StructureNode => ({ id, node_type, data });
const edge = (source: string, target: string, data = {}) => ({ source, target, data });

describe("domain subtree direction fixtures", () => {
  for (const fixture of fixtures) for (const direction of ["outgoing", "incoming", "any"] as SubtreeDirection[]) {
    it(`${fixture.name}: ${direction}`, () => {
      expect([...walkSubtree(fixture.root, subtreeAdjacency(fixture.edges, direction))].sort()).toEqual(fixture[direction]);
    });
  }
});

describe("folded canvas projection", () => {
  it("hides descendants and their evidence, retaining the root and full canonical state", () => {
    const nodes = {
      root: { ...node("root", { collapsed: true }), x: 30, y: 40 },
      child: { ...node("child"), x: 400, y: 800 }, leaf: node("leaf"), doc: node("doc", {}, "document"),
    };
    const edges = [edge("root", "child"), edge("child", "leaf"), edge("child", "doc", { kind: "evidence" }), edge("root", "doc", { kind: "evidence" })];
    const saved = JSON.stringify({ nodes, edges });
    const { hidden } = foldedGraph(nodes, edges);
    expect([...hidden].sort()).toEqual(["child", "leaf"]);
    expect(edges.filter((e) => !hidden.has(e.source) && !hidden.has(e.target))).toEqual([edges[3]]);
    expect(JSON.stringify({ nodes, edges })).toBe(saved);
    const expanded = { ...nodes, root: { ...nodes.root, data: { collapsed: false } } };
    expect(foldedGraph(expanded, edges).hidden.size).toBe(0);
    expect(expanded.child).toEqual(nodes.child);
  });

  it("keeps a shared branch visible through an expanded parent", () => {
    const nodes = { a: node("a", { collapsed: true }), b: node("b"), shared: node("shared"), leaf: node("leaf"), private: node("private") };
    const edges = [edge("a", "shared"), edge("b", "shared"), edge("shared", "leaf"), edge("a", "private")];
    expect([...foldedGraph(nodes, edges).hidden]).toEqual(["private"]);
    nodes.b = node("b", { collapsed: true });
    expect([...foldedGraph(nodes, edges).hidden].sort()).toEqual(["leaf", "private", "shared"]);
  });

  it("does not let a hidden expanded parent rescue another hidden subtree", () => {
    const nodes = { a: node("a", { collapsed: true }), b: node("b"), c: node("c", { collapsed: true }), shared: node("shared") };
    const edges = [edge("a", "b"), edge("b", "shared"), edge("c", "shared")];
    expect([...foldedGraph(nodes, edges).hidden].sort()).toEqual(["b", "shared"]);
  });

  it("breaks cycles without hiding the collapsed root or losing its expand button", () => {
    const nodes = { root: node("root", { collapsed: true }), a: node("a"), b: node("b") };
    const edges = [edge("root", "a"), edge("a", "b"), edge("b", "root")];
    expect([...foldedGraph(nodes, edges).hidden].sort()).toEqual(["a", "b"]);
    nodes.a = node("a", { collapsed: true });
    expect(foldedGraph(nodes, edges).hidden.size).toBe(2);
  });

  it("honors incoming, any, nested parents and deleted endpoints", () => {
    const nodes = { boss: node("boss", { collapsed: true, collapse_direction: "incoming" }), staff: node("staff"), separate: node("separate") };
    expect([...foldedGraph(nodes, [edge("staff", "boss"), edge("ghost", "staff")]).hidden]).toEqual(["staff"]);
    const grouped = { ...nodes, boss: node("boss", { collapsed: true }), staff: { ...node("staff"), parent: "boss" } };
    expect([...foldedGraph(grouped, []).hidden]).toEqual(["staff"]);
    grouped.boss = node("boss", { collapsed: true, collapse_direction: "any" });
    expect([...foldedGraph(grouped, [edge("staff", "boss")]).hidden]).toEqual(["staff"]);
  });

  it("folds document evidence dependents without folding an unrelated document", () => {
    const nodes = { doc: node("doc", { collapsed: true }, "document"), fact: node("fact"), leaf: node("leaf"), other: node("other", {}, "document") };
    expect([...foldedGraph(nodes, [edge("fact", "doc", { kind: "evidence" }), edge("fact", "leaf"), edge("fact", "other", { kind: "evidence" })]).hidden].sort()).toEqual(["fact", "leaf"]);
  });
});

it("summarizes the first useful line without expanding a whole body", () => {
  expect(cardSummary({ text: " First line\nLong second line" })).toBe("First line");
  expect(cardSummary({ rows: [null, { key: "Speed" }] })).toBe("2 rows");
});
