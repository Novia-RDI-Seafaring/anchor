import type { Reference, SourceRef } from "@/stores/canvasStore";

import { api } from "./client";

/**
 * Browser event the references store dispatches after a successful mutate
 * (create / remove / update). The References panel listens for it to refetch
 * without a server round-trip on every render. `detail.slug` is the canvas the
 * mutation hit so a listener can ignore events for other canvases.
 *
 * This is a UI-only nudge, not the source of truth: the panel still refetches
 * via `references.list`. It complements the workspace SSE (which carries the
 * canvas graph, not the metadata bibliography) so a reference made in the PDF
 * dock shows up in the panel in the same window immediately.
 */
export const REFERENCES_CHANGED_EVENT = "anchor:references-changed";

export function emitReferencesChanged(slug: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(REFERENCES_CHANGED_EVENT, { detail: { slug } }),
  );
}

/**
 * Canvas-scoped references API (the human authoring surface for #147 / #110b).
 *
 * Wraps the same HTTP endpoints the MCP / CLI adapters call:
 *   - `GET    /api/workspaces/{slug}/references`        -> list the bibliography
 *   - `POST   /api/workspaces/{slug}/references`        -> author one reference
 *   - `DELETE /api/workspaces/{slug}/references/{id}`   -> remove one reference
 *   - `PATCH  /api/workspaces/{slug}/references/{id}`   -> rename its label
 *
 * `create` posts a `{source_ref, label?, created_by}` body; the server assigns
 * the id + `created_at` and returns the stored `Reference`. `remove` / `update`
 * return the post-mutation envelope `{event, state}`; the panel only needs the
 * success signal so the result is typed loosely. The store schema is owned by
 * #147 (slice 1) and is NOT changed here — `update` edits only the label.
 */
export const references = {
  list: (canvasSlug: string) =>
    api.get<Reference[]>(`/api/workspaces/${canvasSlug}/references`),
  create: async (
    canvasSlug: string,
    body: { source_ref: SourceRef; label?: string; created_by?: "human" | "agent" },
  ) => {
    const created = await api.post<Reference>(
      `/api/workspaces/${canvasSlug}/references`,
      {
        source_ref: body.source_ref,
        label: body.label,
        created_by: body.created_by ?? "human",
      },
    );
    emitReferencesChanged(canvasSlug);
    return created;
  },
  remove: async (canvasSlug: string, referenceId: string) => {
    const res = await api.del<unknown>(
      `/api/workspaces/${canvasSlug}/references/${referenceId}`,
    );
    emitReferencesChanged(canvasSlug);
    return res;
  },
  update: async (
    canvasSlug: string,
    referenceId: string,
    body: { label: string | null },
  ) => {
    const res = await api.patch<unknown>(
      `/api/workspaces/${canvasSlug}/references/${referenceId}`,
      { label: body.label },
    );
    emitReferencesChanged(canvasSlug);
    return res;
  },
};
