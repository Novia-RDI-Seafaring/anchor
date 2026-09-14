/**
 * CanvasSse presence tests (#322 follow-up).
 *
 * Presence rides the existing canvas stream, so the risk worth pinning is
 * regression rather than the feature: snapshot and patch must keep flowing
 * untouched, the actor query params must be omitted entirely when the
 * caller passes no options (so the server's human/"browser" default
 * stands), and a malformed presence frame must not take the stream down.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CanvasSse } from "./sseClient";

type Listener = (ev: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onerror: ((err: Event) => void) | null = null;
  closed = false;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: Listener) {
    (this.listeners[type] ??= []).push(fn);
  }

  emit(type: string, data: string) {
    for (const fn of this.listeners[type] ?? []) fn({ data } as MessageEvent);
  }

  close() {
    this.closed = true;
  }
}

const latest = () => FakeEventSource.instances.at(-1)!;

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CanvasSse presence", () => {
  it("omits the actor query params when no options are given", () => {
    new CanvasSse("w1", {}).connect();
    expect(latest().url).toMatch(/\/api\/workspaces\/w1\/events$/);
  });

  it("announces the caller's actor kind and label on the stream URL", () => {
    new CanvasSse("w1", {}, { actorKind: "human", actorLabel: "monitor" }).connect();
    const url = new URL(latest().url, "http://localhost");
    expect(url.searchParams.get("actor_kind")).toBe("human");
    expect(url.searchParams.get("actor_label")).toBe("monitor");
  });

  it("delivers the full roster on each presence event", () => {
    const onPresence = vi.fn();
    new CanvasSse("w1", { onPresence }).connect();
    latest().emit(
      "presence",
      JSON.stringify({
        workspace: "w1",
        present: [{ client_id: "c1", kind: "human", label: "browser", connected_at: 1, via: "sse" }],
        you: "c1",
      }),
    );
    expect(onPresence).toHaveBeenCalledTimes(1);
    const payload = onPresence.mock.calls[0]![0];
    expect(payload.you).toBe("c1");
    expect(payload.present).toHaveLength(1);
  });

  it("keeps snapshot and patch reconciliation intact around presence frames", () => {
    const onSnapshot = vi.fn();
    const onPatch = vi.fn();
    const onPresence = vi.fn();
    new CanvasSse("w1", { onSnapshot, onPatch, onPresence }).connect();
    const es = latest();

    es.emit("snapshot", JSON.stringify({ slug: "w1", version: 3, nodes: [], edges: [] }));
    es.emit("presence", JSON.stringify({ workspace: "w1", present: [], you: "c1" }));
    es.emit("patch", JSON.stringify({ id: "e1", type: "NodeAdded", version: 4, payload: {} }));

    expect(onSnapshot).toHaveBeenCalledTimes(1);
    expect(onPatch).toHaveBeenCalledTimes(1);
    expect(onPatch.mock.calls[0]![0].version).toBe(4);
    expect(onPresence).toHaveBeenCalledTimes(1);
  });

  it("ignores a malformed presence frame without disturbing later patches", () => {
    const onPatch = vi.fn();
    const onPresence = vi.fn();
    new CanvasSse("w1", { onPatch, onPresence }).connect();
    const es = latest();

    expect(() => es.emit("presence", "not json")).not.toThrow();
    expect(onPresence).not.toHaveBeenCalled();
    es.emit("patch", JSON.stringify({ id: "e1", type: "NodeAdded", version: 1, payload: {} }));
    expect(onPatch).toHaveBeenCalledTimes(1);
  });
});
