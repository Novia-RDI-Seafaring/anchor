import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { INTENTS_CHANGED_EVENT } from "@/api/intents";
import { CanvasSse } from "@/realtime/sseClient";
import type { NodeLike } from "../preview";
import type { ThreadItem } from "../../intent-overlay";
import { useAnchorOverlayHost } from "./AnchorHost";

const geometry = {
  storeNodes: {} as Record<string, NodeLike>, storeEdges: {},
  viewport: { x: 0, y: 0, zoom: 1 },
  getViewport: vi.fn(), setViewport: vi.fn(), toFlow: vi.fn(), rowsOf: vi.fn(), edgesOf: vi.fn(),
};
vi.mock("./AnchorGeometry", () => ({ useAnchorGeometry: () => geometry }));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  private listeners: Record<string, ((event: MessageEvent) => void)[]> = {};

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: (event: MessageEvent) => void) {
    (this.listeners[name] ??= []).push(listener);
  }

  emit(name: string, payload: unknown) {
    for (const listener of this.listeners[name] ?? []) {
      listener({ data: JSON.stringify(payload) } as MessageEvent);
    }
  }

  close() { this.closed = true; }
}

const releases: (() => void)[] = [];
const activeSources = () => FakeEventSource.instances.filter((source) => !source.closed);

beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  cleanup();
  for (const release of releases.splice(0)) release();
  expect(activeSources()).toHaveLength(0);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Anchor suggestion preview feedback", () => {
  it("passes live missing-target feedback to the independent overlay without changing the operation", () => {
    geometry.storeNodes = { card: { id: "card", x: 10, y: 20, label: "Before" } };
    const suggestion: ThreadItem = {
      id: "suggestion", type: "suggestion", author: { kind: "agent" }, created_at: 1,
      text: "Rename the card", state: "pending",
      ops: [{ type: "NodeUpdated", payload: { id: "card", fields: { label: "After" } } }],
    };
    const original = structuredClone(suggestion);
    const { result, rerender } = renderHook(() => useAnchorOverlayHost("canvas", []));
    expect(result.current.display.preview(suggestion)).toMatchObject({
      stale: false, nodes: [{ id: "card", kind: "updated", label: "After" }],
    });
    geometry.storeNodes = { card: { id: "card", x: 30, y: 40, label: "Still here" } };
    rerender();
    expect(result.current.display.preview(suggestion)?.stale).toBe(false);
    geometry.storeNodes = {};
    rerender();
    expect(result.current.display.preview(suggestion)).toEqual({ stale: true, nodes: [], edges: [] });
    expect(suggestion).toEqual(original);
  });
});

describe("Anchor thread change notifications", () => {
  it("nudges pulls for same-count server signals without a local event or polling", () => {
    const canvas = new CanvasSse("canvas", {});
    canvas.connect();
    releases.push(() => canvas.disconnect());
    const { result } = renderHook(() => useAnchorOverlayHost("canvas", []));
    const onChanged = vi.fn();
    releases.push(result.current.thread.subscribeChanged(onChanged));
    expect(FakeEventSource.instances).toHaveLength(1);

    const source = activeSources()[0]!;
    source.emit("intent_pending", { count: 1 });
    source.emit("intent_pending", { count: 1 });
    expect(onChanged).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("removes local and SSE listeners while leaving the canvas subscription live", () => {
    const onPatch = vi.fn();
    const canvas = new CanvasSse("canvas", { onPatch });
    canvas.connect();
    releases.push(() => canvas.disconnect());
    const { result } = renderHook(() => useAnchorOverlayHost("canvas", []));
    const onChanged = vi.fn();
    const unsubscribe = result.current.thread.subscribeChanged(onChanged);
    releases.push(unsubscribe);
    const source = activeSources()[0]!;

    window.dispatchEvent(new Event(INTENTS_CHANGED_EVENT));
    expect(onChanged).toHaveBeenCalledOnce();
    unsubscribe();
    source.emit("intent_pending", { count: 1 });
    window.dispatchEvent(new Event(INTENTS_CHANGED_EVENT));
    source.emit("patch", { type: "NodeUpdated", version: 2 });
    expect(onChanged).toHaveBeenCalledOnce();
    expect(onPatch).toHaveBeenCalledWith({ type: "NodeUpdated", version: 2 });
    expect(source.closed).toBe(false);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("receives thread signals after the shared transport reconnects", () => {
    const canvas = new CanvasSse("canvas", {});
    canvas.connect();
    releases.push(() => canvas.disconnect());
    const { result } = renderHook(() => useAnchorOverlayHost("canvas", []));
    const onChanged = vi.fn();
    releases.push(result.current.thread.subscribeChanged(onChanged));

    activeSources()[0]!.onerror?.(new Event("error"));
    expect(activeSources()).toHaveLength(0);
    vi.advanceTimersByTime(1000);
    expect(activeSources()).toHaveLength(1);
    expect(FakeEventSource.instances).toHaveLength(2);
    activeSources()[0]!.emit("intent_pending", { count: 1 });
    expect(onChanged).toHaveBeenCalledOnce();
  });
});
