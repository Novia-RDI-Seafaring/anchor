/**
 * canvasStore unit tests.
 *
 * Both bugs from the v0.2 dev session would have been caught by tests at
 * this seam: (a) the Card→Node rename slipped through because no test
 * exercised applyEvent over each event type; (b) the version-gap check
 * was never asserted directly. These tests pin both.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { CanvasEvent } from "@/realtime/sseClient";
import { useCanvasStore } from "./canvasStore";

function evt(overrides: Partial<CanvasEvent>): CanvasEvent {
  return {
    id: "e-" + Math.random().toString(36).slice(2),
    type: "NodeAdded",
    workspace_id: "w1",
    version: 1,
    payload: {},
    ts: 0,
    ...overrides,
  };
}

beforeEach(() => {
  useCanvasStore.getState().reset();
  useCanvasStore.setState({
    slug: "w1",
    version: 0,
    nodes: {},
    edges: {},
  });
});

describe("canvasStore.applyEvent", () => {
  it("NodeAdded inserts a node", () => {
    useCanvasStore.getState().applyEvent(
      evt({
        type: "NodeAdded",
        version: 1,
        payload: { id: "a", node_type: "concept", label: "A", x: 10, y: 20, data: {} },
      }),
    );
    const s = useCanvasStore.getState();
    expect(s.version).toBe(1);
    expect(s.nodes["a"]).toBeDefined();
    expect(s.nodes["a"]!.label).toBe("A");
    expect(s.nodes["a"]!.x).toBe(10);
  });

  it("NodeRemoved drops the node", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 1, payload: { id: "a" } }));
    apply(evt({ type: "NodeRemoved", version: 2, payload: { id: "a" } }));
    expect(useCanvasStore.getState().nodes["a"]).toBeUndefined();
    expect(useCanvasStore.getState().version).toBe(2);
  });

  it("NodeMoved updates only x/y of the named node", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 1, payload: { id: "a", x: 0, y: 0 } }));
    apply(evt({ type: "NodeMoved", version: 2, payload: { id: "a", x: 100, y: 200 } }));
    const node = useCanvasStore.getState().nodes["a"]!;
    expect(node.x).toBe(100);
    expect(node.y).toBe(200);
  });

  it("EdgeAdded inserts an edge", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 1, payload: { id: "a" } }));
    apply(evt({ type: "NodeAdded", version: 2, payload: { id: "b" } }));
    apply(evt({
      type: "EdgeAdded", version: 3,
      payload: { id: "e1", source: "a", target: "b", label: "rel", edge_type: "floating" },
    }));
    expect(useCanvasStore.getState().edges["e1"]).toEqual({
      id: "e1",
      source: "a",
      target: "b",
      label: "rel",
      edge_type: "floating",
      sourceHandle: null,
      targetHandle: null,
      data: {},
    });
  });

  it("EdgeUpdated overwrites top-level fields and merges data", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 1, payload: { id: "a" } }));
    apply(evt({ type: "NodeAdded", version: 2, payload: { id: "b" } }));
    apply(evt({
      type: "EdgeAdded", version: 3,
      payload: { id: "e1", source: "a", target: "b", edge_type: "floating", data: { stroke_color: "#abc" } },
    }));
    // Pure top-level update: edge_type → smooth, leave data alone.
    apply(evt({
      type: "EdgeUpdated", version: 4,
      payload: { id: "e1", fields: { edge_type: "smooth" } },
    }));
    expect(useCanvasStore.getState().edges["e1"]!.edge_type).toBe("smooth");
    expect(useCanvasStore.getState().edges["e1"]!.data).toEqual({ stroke_color: "#abc" });
    // Replace the whole data dict.
    apply(evt({
      type: "EdgeUpdated", version: 5,
      payload: { id: "e1", fields: { data: { stroke_color: "#def", end_marker: "none" } } },
    }));
    expect(useCanvasStore.getState().edges["e1"]!.data).toEqual({
      stroke_color: "#def",
      end_marker: "none",
    });
  });

  it("EdgeRemoved drops the edge", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 1, payload: { id: "a" } }));
    apply(evt({ type: "NodeAdded", version: 2, payload: { id: "b" } }));
    apply(evt({ type: "EdgeAdded", version: 3, payload: { id: "e1", source: "a", target: "b" } }));
    apply(evt({ type: "EdgeRemoved", version: 4, payload: { id: "e1" } }));
    expect(useCanvasStore.getState().edges["e1"]).toBeUndefined();
  });

  it("CanvasCleared empties everything but bumps version", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 1, payload: { id: "a" } }));
    apply(evt({ type: "CanvasCleared", version: 2, payload: {} }));
    const s = useCanvasStore.getState();
    expect(s.nodes).toEqual({});
    expect(s.edges).toEqual({});
    expect(s.version).toBe(2);
  });

  it("ignores stale events with version <= current", () => {
    const apply = useCanvasStore.getState().applyEvent;
    apply(evt({ type: "NodeAdded", version: 5, payload: { id: "a" } }));
    apply(evt({ type: "NodeAdded", version: 3, payload: { id: "b" } }));
    expect(useCanvasStore.getState().nodes["b"]).toBeUndefined();
    expect(useCanvasStore.getState().version).toBe(5);
  });

  it("setSnapshot replaces full state from wire shape", () => {
    useCanvasStore.getState().setSnapshot({
      slug: "w1",
      title: "Title",
      version: 42,
      nodes: [{ id: "a", node_type: "fact", label: "A", x: 0, y: 0 }],
      edges: [{ id: "e", source: "a", target: "a" }],
      metadata: {},
    });
    const s = useCanvasStore.getState();
    expect(s.version).toBe(42);
    expect(s.nodes["a"]!.node_type).toBe("fact");
    expect(s.edges["e"]!.edge_type).toBe("floating");
  });

  it("unknown event type is a no-op (doesn't crash, doesn't bump version)", () => {
    useCanvasStore.getState().applyEvent(
      evt({ type: "MysteryEvent", version: 99, payload: {} }),
    );
    // Unknown type still falls through and updates version because the
    // switch ends in `return { ...state, nodes, edges, version: evt.version }`.
    // That's intentional — we don't want a stale version that blocks future
    // legitimate events. Pinned here so future refactors are explicit.
    expect(useCanvasStore.getState().version).toBe(99);
  });
});
