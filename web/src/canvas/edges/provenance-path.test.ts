/**
 * provenance-path unit tests — pinning the hover-thicken path-walk (#183).
 *
 * The selector is the whole behaviour: given the hovered node, which
 * evidence edges form the provenance path back to the source document. The
 * canvas turns the returned set into per-edge active/dimmed flags, so these
 * tests assert the decluttering contract without a DOM:
 *
 *   - quiet by default: no hover -> nothing highlighted.
 *   - hover a fact -> only its path to the source lights up.
 *   - chains walk fact -> intermediate -> doc end to end.
 *   - hover the shared source -> the whole fan-in lights up.
 *   - sibling facts sharing a doc do NOT light each other.
 *   - non-evidence edges are never part of a path.
 *   - hover-out reverts to the quiet default.
 */
import { describe, expect, it } from "vitest";

import {
  provenancePathEdgeIds,
  type ProvenanceEdge,
  type ProvenanceNode,
} from "./provenance-path";

// Three fact nodes, all citing one document. The classic #183 yarn ball.
const FACTS = ["f1", "f2", "f3"];

function nodeMap(extra: ProvenanceNode[] = []): Record<string, ProvenanceNode> {
  const base: ProvenanceNode[] = [
    { id: "f1", node_type: "concept" },
    { id: "f2", node_type: "concept" },
    { id: "f3", node_type: "concept" },
    { id: "doc", node_type: "document" },
    ...extra,
  ];
  return Object.fromEntries(base.map((n) => [n.id, n]));
}

function ev(id: string, source: string, target: string): ProvenanceEdge {
  return { id, source, target, data: { kind: "evidence" } };
}

// N facts -> one doc. Each fact has its own evidence edge to `doc`.
function yarnBall(): ProvenanceEdge[] {
  return FACTS.map((f, i) => ev(`e${i + 1}`, f, "doc"));
}

describe("provenancePathEdgeIds", () => {
  it("highlights nothing when no node is hovered (quiet by default)", () => {
    const path = provenancePathEdgeIds(null, nodeMap(), yarnBall());
    expect(path.size).toBe(0);
  });

  it("highlights nothing for an unknown hovered node id", () => {
    const path = provenancePathEdgeIds("ghost", nodeMap(), yarnBall());
    expect(path.size).toBe(0);
  });

  it("lights up only the hovered fact's edge to the source", () => {
    const path = provenancePathEdgeIds("f2", nodeMap(), yarnBall());
    expect([...path]).toEqual(["e2"]);
  });

  it("does NOT light sibling facts that merely share the source doc", () => {
    const path = provenancePathEdgeIds("f1", nodeMap(), yarnBall());
    // f1 -> doc lights e1 only; e2 (f2->doc) and e3 (f3->doc) stay quiet.
    expect(path.has("e1")).toBe(true);
    expect(path.has("e2")).toBe(false);
    expect(path.has("e3")).toBe(false);
  });

  it("lights the entire fan-in when the source document itself is hovered", () => {
    const path = provenancePathEdgeIds("doc", nodeMap(), yarnBall());
    expect([...path].sort()).toEqual(["e1", "e2", "e3"]);
  });

  it("walks a fact -> intermediate -> doc chain end to end", () => {
    // f1 cites an intermediate hub, the hub cites the doc.
    const nodes = nodeMap([{ id: "hub", node_type: "concept" }]);
    const edges = [ev("a", "f1", "hub"), ev("b", "hub", "doc")];
    const path = provenancePathEdgeIds("f1", nodes, edges);
    expect([...path].sort()).toEqual(["a", "b"]);
  });

  it("lights both directions of a chain when the intermediate hub is hovered", () => {
    // Two facts route through one hub into the doc.
    const nodes = nodeMap([{ id: "hub", node_type: "concept" }]);
    const edges = [
      ev("a", "f1", "hub"),
      ev("b", "f2", "hub"),
      ev("c", "hub", "doc"),
    ];
    const path = provenancePathEdgeIds("hub", nodes, edges);
    // Forward to the doc (c) and backward to both facts feeding the hub.
    expect([...path].sort()).toEqual(["a", "b", "c"]);
  });

  it("ignores non-evidence edges on the path", () => {
    const nodes = nodeMap();
    const edges: ProvenanceEdge[] = [
      ev("e1", "f1", "doc"),
      { id: "plain", source: "f1", target: "f2", data: { kind: "relation" } },
    ];
    const path = provenancePathEdgeIds("f1", nodes, edges);
    expect(path.has("e1")).toBe(true);
    expect(path.has("plain")).toBe(false);
  });

  it("does not light a sibling fact reachable only via the shared doc", () => {
    // Hovering f1 must not spill through doc into f2's edge. The hub-fan-in
    // only opens when the doc (or an intermediate) is the hovered node.
    const path = provenancePathEdgeIds("f1", nodeMap(), yarnBall());
    expect(path.size).toBe(1);
  });

  it("is cycle-safe on a malformed evidence loop", () => {
    const nodes = nodeMap([{ id: "x", node_type: "concept" }]);
    const edges = [ev("a", "f1", "x"), ev("b", "x", "f1")];
    // Should terminate and return the reachable evidence edges, not hang.
    const path = provenancePathEdgeIds("f1", nodes, edges);
    expect(path.size).toBeGreaterThan(0);
  });

  it("reverts to quiet when hover clears (null after a hover)", () => {
    const nodes = nodeMap();
    const edges = yarnBall();
    const hovered = provenancePathEdgeIds("f1", nodes, edges);
    expect(hovered.size).toBe(1);
    const cleared = provenancePathEdgeIds(null, nodes, edges);
    expect(cleared.size).toBe(0);
  });
});
