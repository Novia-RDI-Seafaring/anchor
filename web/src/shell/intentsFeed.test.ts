/**
 * intentsFeed tests (#323) — the Intents panel's data layer.
 *
 * Pure helpers: queue ordering (open oldest-first, resolved newest-first and
 * capped), row titles per kind, resolution text preference, target node ref.
 * Hook: initial fetch, refetch on the SSE `intent_pending` signal, refetch on
 * the same-window changed event, and the polling fallback that catches
 * cross-process mutations (an agent resolving over stdio MCP).
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as intentsApi from "@/api/intents";
import { INTENTS_CHANGED_EVENT, type Intent } from "@/api/intents";

import {
  INTENTS_POLL_MS,
  intentTitle,
  kindLabel,
  resolutionText,
  splitIntents,
  targetNodeId,
  timeAgo,
  useIntentsFeed,
} from "./intentsFeed";

function makeIntent(over: Partial<Intent> = {}): Intent {
  return {
    id: "i1",
    kind: "user_request",
    origin_canvas_id: "plant",
    target: null,
    payload: { text: "extract the pump curves" },
    status: "pending",
    created_at: 100,
    ...over,
  };
}

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

describe("splitIntents", () => {
  it("orders open oldest-first (the agent's drain order) and resolved newest-first", () => {
    const all = [
      makeIntent({ id: "b", created_at: 2 }),
      makeIntent({ id: "a", created_at: 1 }),
      makeIntent({ id: "r2", created_at: 20, status: "resolved" }),
      makeIntent({ id: "r1", created_at: 10, status: "resolved" }),
    ];
    const { open, resolved } = splitIntents(all);
    expect(open.map((i) => i.id)).toEqual(["a", "b"]);
    expect(resolved.map((i) => i.id)).toEqual(["r2", "r1"]);
  });

  it("caps the recently-resolved section", () => {
    const all = Array.from({ length: 5 }, (_, n) =>
      makeIntent({ id: `r${n}`, created_at: n, status: "resolved" }),
    );
    expect(splitIntents(all, 2).resolved.map((i) => i.id)).toEqual(["r4", "r3"]);
  });
});

describe("row helpers", () => {
  it("titles a user_request with its text", () => {
    expect(intentTitle(makeIntent())).toBe("extract the pump curves");
  });

  it("titles a drop_to_ingest with the dropped file", () => {
    const intent = makeIntent({
      kind: "drop_to_ingest",
      payload: { filename: "pump.pdf", slug: "pump" },
    });
    expect(intentTitle(intent)).toBe("Ingest pump.pdf");
  });

  it("falls back to a humanized kind label", () => {
    expect(intentTitle(makeIntent({ kind: "make_reference", payload: {} }))).toBe(
      "Make reference",
    );
    expect(kindLabel("some_future_kind")).toBe("some future kind");
  });

  it("reads the target node ref off the payload", () => {
    expect(targetNodeId(makeIntent())).toBeNull();
    expect(
      targetNodeId(makeIntent({ payload: { text: "t", workspace_id: "plant", node_id: "n7" } })),
    ).toBe("n7");
  });

  it("prefers human-readable resolution keys, then falls back to compact JSON", () => {
    expect(resolutionText(makeIntent())).toBeNull();
    expect(
      resolutionText(makeIntent({ status: "resolved", result: { note: "done" } })),
    ).toBe("done");
    expect(
      resolutionText(makeIntent({ status: "resolved", result: { dismissed: true } })),
    ).toBe("dismissed");
    expect(
      resolutionText(makeIntent({ status: "resolved", result: { rows: 3 } })),
    ).toBe('{"rows":3}');
    expect(resolutionText(makeIntent({ status: "resolved", result: {} }))).toBeNull();
  });

  it("formats a compact relative age", () => {
    const nowMs = 1_000_000 * 1000;
    expect(timeAgo(1_000_000 - 10, nowMs)).toBe("just now");
    expect(timeAgo(1_000_000 - 120, nowMs)).toBe("2m ago");
    expect(timeAgo(1_000_000 - 7200, nowMs)).toBe("2h ago");
    expect(timeAgo(0, nowMs)).toBe("");
  });
});

describe("useIntentsFeed", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("fetches on mount and splits open vs resolved", async () => {
    vi.spyOn(intentsApi.intents, "listAll").mockResolvedValue([
      makeIntent({ id: "open-1" }),
      makeIntent({ id: "done-1", status: "resolved", result: { note: "ok" } }),
    ]);

    const { result, unmount } = renderHook(() => useIntentsFeed());
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    expect(result.current.open.map((i) => i.id)).toEqual(["open-1"]);
    expect(result.current.resolved.map((i) => i.id)).toEqual(["done-1"]);
    expect(result.current.openCount).toBe(1);
    unmount();
  });

  it("refetches when the SSE intent_pending signal fires (live transitions)", async () => {
    const listAll = vi
      .spyOn(intentsApi.intents, "listAll")
      .mockResolvedValue([makeIntent({ id: "open-1" })]);

    const { result, unmount } = renderHook(() => useIntentsFeed());
    await waitFor(() => expect(result.current.openCount).toBe(1));

    // An agent resolves it elsewhere; the server re-emits the count signal.
    listAll.mockResolvedValue([
      makeIntent({ id: "open-1", status: "resolved", result: { note: "handled" } }),
    ]);
    act(() => {
      FakeEventSource.instances[0]!.emit("intent_pending", JSON.stringify({ count: 0 }));
    });

    await waitFor(() => expect(result.current.openCount).toBe(0));
    expect(result.current.resolved.map((i) => i.id)).toEqual(["open-1"]);
    unmount();
    expect(FakeEventSource.instances[0]!.closed).toBe(true);
  });

  it("refetches on the same-window intents-changed nudge", async () => {
    const listAll = vi.spyOn(intentsApi.intents, "listAll").mockResolvedValue([]);
    const { unmount } = renderHook(() => useIntentsFeed());
    await waitFor(() => expect(listAll).toHaveBeenCalled());

    const before = listAll.mock.calls.length;
    act(() => {
      window.dispatchEvent(new CustomEvent(INTENTS_CHANGED_EVENT));
    });
    await waitFor(() => expect(listAll.mock.calls.length).toBeGreaterThan(before));
    unmount();
  });

  it("polls as a fallback for cross-process mutations", async () => {
    vi.useFakeTimers();
    const listAll = vi.spyOn(intentsApi.intents, "listAll").mockResolvedValue([]);
    const { unmount } = renderHook(() => useIntentsFeed());
    await act(async () => {
      await Promise.resolve();
    });

    const before = listAll.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(INTENTS_POLL_MS);
    });
    expect(listAll.mock.calls.length).toBeGreaterThan(before);
    unmount();
  });

  it("surfaces a fetch failure as the feed error", async () => {
    vi.spyOn(intentsApi.intents, "listAll").mockRejectedValue(new Error("boom"));
    const { result, unmount } = renderHook(() => useIntentsFeed());
    await waitFor(() => expect(result.current.error).toContain("boom"));
    unmount();
  });
});
