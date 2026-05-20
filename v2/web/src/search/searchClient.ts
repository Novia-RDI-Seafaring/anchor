/**
 * Search HTTP client.
 *
 * Talks to `GET /api/documents/_search?q=...&k=...` which the backend
 * resolves against `gold/<slug>/embeddings.json`. The server reports the
 * `embed_model` it used; we cross-check against our own canonical id and
 * refuse to surface results from a mismatched model — cross-embedding-
 * space cosine scores are nonsense and would silently rank garbage near
 * the top.
 *
 * The query is sent as plain text. The server embeds it (or expects a
 * pre-embedded vector under a future endpoint). The browser-side query
 * embedder in `embedder.ts` is for client-side re-ranking and for the
 * /search input which will land in a later PR; this client doesn't yet
 * push a vector over the wire.
 */

import { api } from "@/api/client";
import { EMBED_MODEL_ID } from "./embedder";

export type SearchHit = {
  slug: string;
  page: number;
  region_id: string;
  text: string;
  score: number;
};

export type SearchResponse = {
  query: string;
  embed_model: string;
  doc_count: number;
  hits: SearchHit[];
};

export async function searchDocuments(query: string, k = 10): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, k: String(k) });
  const rsp = await api.get<SearchResponse>(`/api/documents/_search?${params.toString()}`);
  if (rsp.embed_model !== EMBED_MODEL_ID) {
    throw new Error(
      `embed model mismatch: server returned "${rsp.embed_model}" but ` +
        `browser embedder is "${EMBED_MODEL_ID}". Cross-model cosine ` +
        `search is invalid — re-ingest with the matching model or ` +
        `update the browser embedder.`,
    );
  }
  return rsp;
}
