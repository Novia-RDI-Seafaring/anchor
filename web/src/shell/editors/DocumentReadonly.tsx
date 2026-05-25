/**
 * DocumentReadonly — read-only metadata view for `document` nodes.
 *
 * Document nodes are sourced from the gold ingestion pipeline (PDF →
 * Docling silver → gold JSON). Editing their slug or filename in the UI
 * is a category error — those fields are content-addressable identifiers
 * for the ingestion store. If the user wants different metadata, they
 * re-ingest.
 *
 * What we show: slug, filename, page count, ingest status, region count.
 * Nothing in this view writes back; there's no debounced PATCH.
 */
import type { EditorProps } from "./_types";

export function DocumentReadonly({ node }: EditorProps) {
  const d = (node.data ?? {}) as {
    slug?: string;
    filename?: string;
    page_count?: number;
    region_count?: number;
    status?: string;
    error?: string;
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded border border-neutral-200 bg-neutral-50 px-3 py-2 text-[11px] text-neutral-600">
        Document metadata comes from the ingestion pipeline. Re-ingest the
        source PDF to change these fields.
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
        <dt className="text-neutral-500">Label</dt>
        <dd className="break-words text-neutral-900">{node.label || "—"}</dd>

        <dt className="text-neutral-500">Slug</dt>
        <dd className="break-all font-mono text-neutral-900">{d.slug ?? "—"}</dd>

        <dt className="text-neutral-500">Filename</dt>
        <dd className="break-all text-neutral-900">{d.filename ?? "—"}</dd>

        <dt className="text-neutral-500">Pages</dt>
        <dd className="text-neutral-900">{d.page_count ?? "—"}</dd>

        <dt className="text-neutral-500">Regions</dt>
        <dd className="text-neutral-900">{d.region_count ?? "—"}</dd>

        <dt className="text-neutral-500">Status</dt>
        <dd className="text-neutral-900">{d.status ?? "ready"}</dd>

        {d.error ? (
          <>
            <dt className="text-red-600">Error</dt>
            <dd className="text-red-700">{d.error}</dd>
          </>
        ) : null}
      </dl>
    </div>
  );
}
