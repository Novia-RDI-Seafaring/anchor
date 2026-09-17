/**
 * Persisted per-node attribution cache (#325): one whole-log fetch per
 * canvas per session, shared between callers, with failed fetches
 * evicted so a later selection can retry.
 */
import { afterEach, expect, it, vi } from "vitest";

import * as canvasesApi from "@/api/canvases";

import { clearTouchedCache, getTouchedMap } from "./persistedAttribution";

afterEach(() => {
  clearTouchedCache();
  vi.restoreAllMocks();
});

it("extracts the touched map from the whole-log fold and caches per slug", async () => {
  const changes = vi.spyOn(canvasesApi.canvases, "changes").mockResolvedValue({
    from_version: 0,
    to_version: 3,
    groups: [],
    touched: { n1: { kind: "agent", label: "claude-code" }, n2: null },
  });

  const a = await getTouchedMap("plant");
  const b = await getTouchedMap("plant");
  expect(a).toEqual({ n1: { kind: "agent", label: "claude-code" }, n2: null });
  expect(b).toBe(a);
  expect(changes).toHaveBeenCalledTimes(1);
  expect(changes).toHaveBeenCalledWith("plant", 0);

  await getTouchedMap("pump");
  expect(changes).toHaveBeenCalledTimes(2);
});

it("answers an empty map when the server omits touched", async () => {
  vi.spyOn(canvasesApi.canvases, "changes").mockResolvedValue({
    from_version: 0,
    to_version: 0,
    groups: [],
  });
  expect(await getTouchedMap("plant")).toEqual({});
});

it("evicts a failed fetch so the next selection retries", async () => {
  const changes = vi
    .spyOn(canvasesApi.canvases, "changes")
    .mockRejectedValueOnce(new Error("boom"))
    .mockResolvedValueOnce({
      from_version: 0,
      to_version: 1,
      groups: [],
      touched: { n1: null },
    });

  await expect(getTouchedMap("plant")).rejects.toThrow("boom");
  expect(await getTouchedMap("plant")).toEqual({ n1: null });
  expect(changes).toHaveBeenCalledTimes(2);
});
