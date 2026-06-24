/**
 * Library — browse OIP-ingested artefacts (documents, CAD models, ...) and
 * drop them onto the canvas as nodes.
 *
 * Hits `/api/documents` and `/api/cad` directly. Any future producer that
 * exposes a list endpoint plugs in here — the library is a federation of
 * per-producer browsers, not Anchor-specific.
 */
import { useEffect, useRef, useState } from "react";

import { cad, type CadModel } from "@/api/cad";
import { documents, type DocumentSummary } from "@/api/documents";

type Props = { workspaceSlug: string };

export function Library({ workspaceSlug: _workspaceSlug }: Props) {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [cads, setCads] = useState<CadModel[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [d, c] = await Promise.all([
          documents.list().catch(() => [] as DocumentSummary[]),
          cad.list().catch(() => [] as CadModel[]),
        ]);
        if (!cancelled) {
          setDocs(d);
          setCads(c);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    };

    refresh();
    // Light polling — every 8s. SSE for documents/cad lists isn't wired yet.
    const id = window.setInterval(refresh, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-3">
      <Section title={`Documents (${docs.length})`} subtitle="anchor_pdfs">
        {docs.length === 0 ? (
          <Empty hint="ingest a PDF — drop it on the canvas or use anchor ingest" />
        ) : (
          docs.map((d) => (
            <DocumentItem
              key={d.slug}
              doc={d}
            />
          ))
        )}
      </Section>

      <Section title={`CAD models (${cads.length})`} subtitle="anchor_cad">
        {cads.length === 0 ? (
          <Empty hint="no CAD models yet — use cad.inspect via MCP" />
        ) : (
          cads.map((c) => (
            <DraggableItem
              key={c.slug}
              label={c.title || c.filename || c.slug}
              hint={`${c.kind}${c.geometry?.triangle_count ? ` · ${c.geometry.triangle_count} tris` : ""}`}
              payload={{
                node_type: "cad:model",
                label: c.title || c.filename || c.slug,
                data: {
                  cad_slug: c.slug,
                  kind: c.kind,
                  parameters: c.parameters?.map((p) => p.name) ?? [],
                },
              }}
            />
          ))
        )}
      </Section>

      {error ? (
        <div className="px-2 text-[10px] text-red-600">error: {error}</div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DocumentItem — a draggable library row for a single document. Shows:
//   - page-1 thumbnail (lazy, fallback on error)
//   - title (primary) + filename (secondary) + slug (tooltip)
//   - hover preview popover with a larger cover image and open-viewer link
// ---------------------------------------------------------------------------

function DocumentItem({ doc }: { doc: DocumentSummary }) {
  const [imgError, setImgError] = useState(false);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewImgError, setPreviewImgError] = useState(false);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const thumbnailUrl = documents.pageImageUrl(doc.slug, 1);
  const hint = `${doc.page_count}p${doc.has_gold ? " · gold" : ""}`;
  const payload = {
    node_type: "document",
    label: doc.title || doc.filename,
    data: {
      slug: doc.slug,
      filename: doc.filename,
      page_count: doc.page_count,
      region_count: doc.region_count,
      status: "ready",
    },
  };

  const showPreview = () => {
    hoverTimerRef.current = setTimeout(() => setPreviewVisible(true), 300);
  };
  const hidePreview = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    setPreviewVisible(false);
  };

  return (
    <div className="relative">
      <div
        draggable
        data-testid="document-item"
        data-slug={doc.slug}
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = "copy";
          e.dataTransfer.setData("application/x-anchor-node", JSON.stringify(payload));
        }}
        onMouseEnter={showPreview}
        onMouseLeave={hidePreview}
        onFocus={showPreview}
        onBlur={hidePreview}
        onContextMenu={(e) => {
          // Right-click shows preview immediately.
          e.preventDefault();
          setPreviewVisible((v) => !v);
        }}
        className="cursor-grab rounded border border-neutral-200 bg-white hover:bg-neutral-50 active:cursor-grabbing"
        title={doc.slug}
      >
        <div className="flex items-center gap-2 px-2 py-1.5">
          {/* Thumbnail */}
          <div className="shrink-0">
            {imgError ? (
              <div
                data-testid="thumbnail-fallback"
                className="flex h-10 w-8 items-center justify-center rounded bg-neutral-100 text-[14px] text-neutral-400"
              >
                ▤
              </div>
            ) : (
              <img
                data-testid="thumbnail-img"
                src={thumbnailUrl}
                alt={doc.filename}
                loading="lazy"
                className="h-10 w-8 rounded object-cover object-top"
                onError={() => setImgError(true)}
              />
            )}
          </div>

          {/* Text */}
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium text-neutral-800">
              {doc.title || doc.slug}
            </div>
            <div className="truncate text-[10px] text-neutral-500" data-testid="doc-filename">
              {doc.filename}
            </div>
            <div className="text-[9px] italic text-neutral-400">{hint}</div>
          </div>
        </div>
      </div>

      {/* Hover preview popover */}
      {previewVisible ? (
        <div
          data-testid="hover-preview"
          className="absolute left-full top-0 z-50 ml-2 w-56 rounded border border-neutral-200 bg-white shadow-lg"
          onMouseEnter={() => {
            if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
          }}
          onMouseLeave={hidePreview}
        >
          <div className="p-1.5">
            {previewImgError ? (
              <div
                className="flex h-36 w-full items-center justify-center rounded bg-neutral-100 text-sm text-neutral-400"
              >
                no preview
              </div>
            ) : (
              <img
                src={thumbnailUrl}
                alt={doc.filename}
                className="w-full rounded"
                onError={() => setPreviewImgError(true)}
              />
            )}
          </div>
          <div className="border-t border-neutral-100 px-2 py-1.5">
            <div className="truncate text-xs font-medium text-neutral-800">
              {doc.title || doc.slug}
            </div>
            <div className="truncate text-[10px] text-neutral-500">{doc.filename}</div>
            <div className="mt-0.5 font-mono text-[9px] text-neutral-400">{doc.slug}</div>
            <div className="mt-0.5 text-[9px] text-neutral-400">
              {doc.page_count} {doc.page_count === 1 ? "page" : "pages"}
              {doc.has_gold ? " · gold" : ""}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between px-2 pt-1 pb-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          {title}
        </div>
        {subtitle ? (
          <div className="text-[9px] italic text-neutral-400">{subtitle}</div>
        ) : null}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Empty({ hint }: { hint: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
      {hint}
    </div>
  );
}

function DraggableItem({
  label,
  hint,
  payload,
}: {
  label: string;
  hint: string;
  payload: { node_type: string; label?: string; data?: Record<string, unknown> };
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData("application/x-anchor-node", JSON.stringify(payload));
      }}
      className="cursor-grab rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs hover:bg-neutral-50 active:cursor-grabbing"
      title={hint}
    >
      <div className="truncate font-medium text-neutral-800">{label}</div>
      <div className="text-[10px] italic text-neutral-500">{hint}</div>
    </div>
  );
}
