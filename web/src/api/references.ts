import type { Reference, SourceRef } from "@/stores/canvasStore";

import { api } from "./client";

/**
 * Canvas-scoped references API (the human authoring surface for #147 / #110b).
 *
 * Wraps the same HTTP endpoints the MCP / CLI adapters call:
 *   - `GET  /api/workspaces/{slug}/references`        -> list the bibliography
 *   - `POST /api/workspaces/{slug}/references`        -> author one reference
 *
 * `create` posts a `{source_ref, label?, created_by}` body; the server assigns
 * the id + `created_at` and returns the stored `Reference`. The store schema is
 * owned by #147 (slice 1) and is NOT changed here.
 */
export const references = {
  list: (canvasSlug: string) =>
    api.get<Reference[]>(`/api/workspaces/${canvasSlug}/references`),
  create: (
    canvasSlug: string,
    body: { source_ref: SourceRef; label?: string; created_by?: "human" | "agent" },
  ) =>
    api.post<Reference>(`/api/workspaces/${canvasSlug}/references`, {
      source_ref: body.source_ref,
      label: body.label,
      created_by: body.created_by ?? "human",
    }),
};
