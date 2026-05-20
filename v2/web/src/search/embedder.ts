/**
 * In-browser query embedder.
 *
 * The Python ingest pipeline embeds gold regions with sentence-transformers
 * + `BAAI/bge-small-en-v1.5` (normalised). To search those vectors from the
 * browser we must produce *the same* embedding for user queries — same
 * model, same pooling (mean), same L2 normalisation. This module is the
 * single source of truth for "how the browser embeds text" in Anchor v2.
 *
 * Implementation:
 *   - A Web Worker (`embedder.worker.ts`) wraps `@xenova/transformers` and
 *     downloads the ONNX-quantised model on first use (~33 MB, cached by
 *     the browser thereafter).
 *   - This module dispatches request/reply messages keyed by an id and
 *     resolves promises off the worker's responses.
 *   - No UI auto-loads the model. Callers either call `embed*` (which
 *     transparently boots the worker) or `prefetchModel()` to warm it at
 *     idle.
 *
 * The model id exported here is the *canonical HuggingFace id*
 * (`BAAI/bge-small-en-v1.5`), not the transformers.js mirror. The server
 * also persists this canonical id in `gold/<slug>/embeddings.json` as
 * `embed_model`. `searchClient.ts` cross-checks the two before issuing a
 * search.
 */

import EmbedderWorker from "./embedder.worker?worker";

export const EMBED_MODEL_ID = "BAAI/bge-small-en-v1.5";
export const EMBED_DIM = 384;

type WorkerOutMessage =
  | { id: string; type: "ready" }
  | { id: string; type: "result"; vectors: number[][] }
  | { id: string; type: "error"; message: string };

type Pending = {
  resolve: (vectors: number[][]) => void;
  reject: (err: Error) => void;
};

let worker: Worker | null = null;
const pending = new Map<string, Pending>();
let readyPromise: Promise<void> | null = null;
let nextId = 0;

function newId(): string {
  nextId += 1;
  return `req-${nextId}`;
}

function getWorker(): Worker {
  if (worker) return worker;
  const w = new EmbedderWorker();
  w.addEventListener("message", (ev: MessageEvent<WorkerOutMessage>) => {
    const msg = ev.data;
    const p = pending.get(msg.id);
    if (!p) return;
    if (msg.type === "result") {
      pending.delete(msg.id);
      p.resolve(msg.vectors);
    } else if (msg.type === "error") {
      pending.delete(msg.id);
      p.reject(new Error(`embedder worker: ${msg.message}`));
    }
    // "ready" is handled separately via readyPromise; no pending entry.
  });
  w.addEventListener("error", (ev) => {
    // Fail all in-flight requests if the worker dies.
    const err = new Error(`embedder worker crashed: ${ev.message}`);
    for (const [id, p] of pending) {
      pending.delete(id);
      p.reject(err);
    }
  });
  worker = w;
  return w;
}

/**
 * Boot the worker and download model weights. Resolves once the pipeline
 * is loaded. Safe to call multiple times — subsequent calls reuse the
 * same in-flight promise.
 */
export function prefetchModel(): Promise<void> {
  if (readyPromise) return readyPromise;
  const w = getWorker();
  readyPromise = new Promise<void>((resolve, reject) => {
    const id = newId();
    const onMessage = (ev: MessageEvent<WorkerOutMessage>) => {
      const msg = ev.data;
      if (msg.id !== id) return;
      w.removeEventListener("message", onMessage);
      if (msg.type === "ready") resolve();
      else if (msg.type === "error") reject(new Error(`embedder init: ${msg.message}`));
    };
    w.addEventListener("message", onMessage);
    w.postMessage({ id, type: "init" });
  });
  return readyPromise;
}

/**
 * Embed a batch of texts. Returns one L2-normalised 384-d vector per
 * input string. Order matches `texts`.
 */
export async function embed(texts: string[]): Promise<number[][]> {
  if (texts.length === 0) return [];
  const w = getWorker();
  return new Promise<number[][]>((resolve, reject) => {
    const id = newId();
    pending.set(id, { resolve, reject });
    w.postMessage({ id, type: "embed", texts });
  });
}

/** Convenience: embed a single query string. */
export async function embedQuery(text: string): Promise<number[]> {
  const out = await embed([text]);
  const vec = out[0];
  if (!vec) throw new Error("embedder returned empty result for single query");
  return vec;
}

/** The canonical embed-model id. Stable across versions. */
export function getEmbedModelId(): string {
  return EMBED_MODEL_ID;
}

// ---- Test hooks (intentionally unexported from the package barrel) -----
// Tests need a way to inject a fake worker. Vite's `?worker` import gives
// us a constructor, but in jsdom no real Worker runs. The helpers below
// let `embedder.test.ts` swap in a stub. They are NOT part of the public
// API; do not import them from application code.

/** @internal */
export function __setWorkerForTests(stub: Worker | null): void {
  worker = stub;
  // Re-attach the message handler if a fresh worker was injected so the
  // promise wiring stays consistent with the production path.
  if (stub) {
    stub.addEventListener("message", (ev: MessageEvent<WorkerOutMessage>) => {
      const msg = ev.data;
      const p = pending.get(msg.id);
      if (!p) return;
      if (msg.type === "result") {
        pending.delete(msg.id);
        p.resolve(msg.vectors);
      } else if (msg.type === "error") {
        pending.delete(msg.id);
        p.reject(new Error(`embedder worker: ${msg.message}`));
      }
    });
  }
}

/** @internal */
export function __resetForTests(): void {
  worker = null;
  pending.clear();
  readyPromise = null;
  nextId = 0;
}
