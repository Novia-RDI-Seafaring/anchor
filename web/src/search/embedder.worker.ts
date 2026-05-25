/**
 * Embedder Web Worker.
 *
 * Runs `@xenova/transformers` off the main thread so the model download
 * (~33 MB the first time) and per-query inference don't jank the UI.
 *
 * Protocol:
 *   - Main → Worker: { id: string, type: "init" | "embed", texts?: string[] }
 *   - Worker → Main:
 *       { id, type: "ready" }                                  // after first load
 *       { id, type: "result", vectors: number[][] }            // embed reply
 *       { id, type: "error", message: string }                 // failure
 *
 * The pipeline is created lazily on the first message. We always call the
 * pipeline with `{ pooling: "mean", normalize: true }` so the returned
 * vectors are L2-normalised — this matches sentence-transformers'
 * `normalize_embeddings=True` on the Python side and lets cosine reduce
 * to a dot product downstream.
 *
 * Model id: `Xenova/bge-small-en-v1.5` (the transformers.js ONNX mirror
 * of `BAAI/bge-small-en-v1.5`). The user-facing model id on the public
 * API is the canonical HF id — see `embedder.ts`.
 */

/// <reference lib="webworker" />

import { pipeline, type FeatureExtractionPipeline } from "@xenova/transformers";

const MODEL_REPO = "Xenova/bge-small-en-v1.5";
const EMBED_DIM = 384;

let pipelinePromise: Promise<FeatureExtractionPipeline> | null = null;

function getPipeline(): Promise<FeatureExtractionPipeline> {
  if (!pipelinePromise) {
    pipelinePromise = pipeline("feature-extraction", MODEL_REPO) as Promise<FeatureExtractionPipeline>;
  }
  return pipelinePromise;
}

type InMessage =
  | { id: string; type: "init" }
  | { id: string; type: "embed"; texts: string[] };

type OutMessage =
  | { id: string; type: "ready" }
  | { id: string; type: "result"; vectors: number[][] }
  | { id: string; type: "error"; message: string };

function post(msg: OutMessage): void {
  (self as unknown as DedicatedWorkerGlobalScope).postMessage(msg);
}

self.addEventListener("message", async (ev: MessageEvent<InMessage>) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      await getPipeline();
      post({ id: msg.id, type: "ready" });
      return;
    }
    if (msg.type === "embed") {
      const extractor = await getPipeline();
      // Mean-pool + L2-normalise inside transformers.js — the bge family
      // is trained for mean pooling and the Python side normalises.
      const output = await extractor(msg.texts, { pooling: "mean", normalize: true });
      // `output.data` is a flat Float32Array of length (N * EMBED_DIM).
      // `output.dims` is [N, EMBED_DIM]. Slice into one array per row.
      const dims = output.dims;
      const rowCount = dims[0] ?? msg.texts.length;
      const cols = dims[1] ?? EMBED_DIM;
      const flat = output.data as Float32Array;
      const vectors: number[][] = [];
      for (let i = 0; i < rowCount; i++) {
        const row = new Array<number>(cols);
        const base = i * cols;
        for (let j = 0; j < cols; j++) {
          row[j] = flat[base + j] ?? 0;
        }
        vectors.push(row);
      }
      post({ id: msg.id, type: "result", vectors });
      return;
    }
  } catch (err) {
    post({
      id: msg.id,
      type: "error",
      message: err instanceof Error ? err.message : String(err),
    });
  }
});

// Make TypeScript treat this file as a module (required for Vite worker import).
export {};
