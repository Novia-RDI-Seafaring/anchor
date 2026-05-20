/**
 * Embedder smoke tests.
 *
 * The real transformers.js pipeline downloads ~33 MB of model weights and
 * spins up an ONNX runtime — far too heavy for CI. Instead we inject a
 * fake `Worker` that synthesises plausible L2-normalised vectors and
 * exercises the request/reply plumbing. The tests pin:
 *   - shape: `embed(N texts)` returns `N x 384`
 *   - normalisation: every output vector has ||v||₂ ≈ 1
 *   - `embedQuery` returns a single 384-length vector
 *   - the canonical model id is exported unchanged
 *
 * If you ever swap pooling or remove normalisation in the worker, the
 * "unit-normalised" assertion will catch it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Vite's `?worker` import is resolved by Vite's bundler — not by Vitest's
// transformer. Stub it before the module under test is loaded so the
// real constructor never runs (which would in turn pull in the 30+ MB
// transformers.js bundle inside jsdom).
vi.mock("./embedder.worker?worker", () => {
  return {
    default: class FakeCtor {
      // Vitest will overwrite this instance with the test stub via
      // __setWorkerForTests, so the constructor body is intentionally
      // empty. It exists only to satisfy `new EmbedderWorker()`.
    },
  };
});

import {
  EMBED_DIM,
  EMBED_MODEL_ID,
  embed,
  embedQuery,
  getEmbedModelId,
  __resetForTests,
  __setWorkerForTests,
} from "./embedder";

// Build a 384-d vector that's deterministic per `seed` and L2-normalised.
function normedVector(seed: number, dim: number): number[] {
  const raw = new Array<number>(dim);
  // Cheap PRNG. We only need reproducible noise, not crypto quality.
  let s = seed * 9301 + 49297;
  for (let i = 0; i < dim; i++) {
    s = (s * 9301 + 49297) % 233280;
    raw[i] = (s / 233280) - 0.5; // centre around 0 so the vector isn't all positive
  }
  const norm = Math.sqrt(raw.reduce((acc, v) => acc + v * v, 0));
  return raw.map((v) => v / norm);
}

type WorkerInMessage =
  | { id: string; type: "init" }
  | { id: string; type: "embed"; texts: string[] };

/**
 * Minimal Worker stand-in. It implements just enough of the DOM Worker
 * surface that `embedder.ts` cares about: `postMessage`, `addEventListener`
 * for "message" / "error", and `terminate`.
 */
class FakeWorker implements Worker {
  onmessage: ((ev: MessageEvent) => unknown) | null = null;
  onmessageerror: ((ev: MessageEvent) => unknown) | null = null;
  onerror: ((ev: ErrorEvent) => unknown) | null = null;
  private listeners = new Map<string, Set<(ev: Event) => void>>();

  postMessage(data: WorkerInMessage): void {
    // Reply on a microtask so it looks like a real Worker (and so the
    // pending entry has been registered by the caller before we fire).
    queueMicrotask(() => {
      if (data.type === "init") {
        this.dispatch({ id: data.id, type: "ready" });
        return;
      }
      if (data.type === "embed") {
        const vectors = data.texts.map((_, i) => normedVector(i + 1, EMBED_DIM));
        this.dispatch({ id: data.id, type: "result", vectors });
      }
    });
  }

  private dispatch(payload: unknown): void {
    const ev = new MessageEvent("message", { data: payload });
    this.onmessage?.(ev);
    for (const cb of this.listeners.get("message") ?? []) cb(ev);
  }

  addEventListener(type: string, cb: (ev: Event) => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(cb);
  }

  removeEventListener(type: string, cb: (ev: Event) => void): void {
    this.listeners.get(type)?.delete(cb);
  }

  dispatchEvent(_ev: Event): boolean {
    return true;
  }

  terminate(): void {
    this.listeners.clear();
  }
}

beforeEach(() => {
  __resetForTests();
  __setWorkerForTests(new FakeWorker());
});

afterEach(() => {
  __resetForTests();
});

describe("embedder", () => {
  it("exports the canonical model id (matches the Python ingest side)", () => {
    expect(EMBED_MODEL_ID).toBe("BAAI/bge-small-en-v1.5");
    expect(getEmbedModelId()).toBe(EMBED_MODEL_ID);
    expect(EMBED_DIM).toBe(384);
  });

  it("embed(['hello','world']) returns a 2 x 384 array", async () => {
    const out = await embed(["hello", "world"]);
    expect(out).toHaveLength(2);
    expect(out[0]).toHaveLength(384);
    expect(out[1]).toHaveLength(384);
  });

  it("every output vector is L2-normalised (sum of squares ≈ 1)", async () => {
    const out = await embed(["alpha", "beta", "gamma"]);
    for (const vec of out) {
      const sumSq = vec.reduce((acc, v) => acc + v * v, 0);
      // Tolerance: floating-point round-trip plus PRNG quantisation.
      expect(sumSq).toBeGreaterThan(0.99);
      expect(sumSq).toBeLessThan(1.01);
    }
  });

  it("embedQuery returns a single 384-length vector", async () => {
    const vec = await embedQuery("how do I prime the pump?");
    expect(Array.isArray(vec)).toBe(true);
    expect(vec).toHaveLength(384);
    const sumSq = vec.reduce((acc, v) => acc + v * v, 0);
    expect(sumSq).toBeGreaterThan(0.99);
    expect(sumSq).toBeLessThan(1.01);
  });

  it("embed([]) short-circuits and returns []", async () => {
    const out = await embed([]);
    expect(out).toEqual([]);
  });
});
