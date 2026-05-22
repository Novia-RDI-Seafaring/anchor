import { useEffect, useMemo, useRef, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { BACKEND_URL } from "@/api/client";
import { documents, type DocumentIndex, type Region } from "@/api/documents";
import { useUiStore } from "@/stores/uiStore";

const STATUS_STYLES: Record<string, string> = {
  pending: "border-amber-400 bg-amber-50",
  ingesting: "border-blue-400 bg-blue-50",
  searching: "border-blue-400 bg-blue-50",
  found: "border-emerald-400 bg-emerald-50",
  failed: "border-red-400 bg-red-50",
  ready: "border-neutral-300 bg-white",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "queued",
  ingesting: "ingesting",
  searching: "ingesting",
  found: "ready",
  failed: "failed",
  ready: "ready",
};

type PageMeta = { width: number; height: number };

// Default DPI used by anchor_pdfs when rendering page PNGs. Matches
// AnchorConfig.dpi. If the producer is reconfigured to a different DPI,
// gold-map should expose it explicitly; for now we assume the default.
const RENDER_DPI = 150;
const POINTS_PER_INCH = 72;

/**
 * DocumentPrimitive — a paginated document viewport on the canvas.
 *
 * Phase A:
 *   - Renders the current page as a PNG with prev/next pagination.
 *   - Overlays an SVG layer showing every region's bbox on that page.
 *   - Each region is hoverable and draggable: drag → spec node materialises
 *     on the canvas with row-level provenance back to this document.
 *   - Click a region → opens the full PDF viewer modal at that region.
 *
 * Phase B (cross-component hover):
 *   - When `useUiStore.hoveredSourceRef` matches this document's slug, the
 *     node auto-flips to the referenced page and highlights the matching
 *     region. Spec nodes broadcast the hover; this node responds.
 */
export function DocumentPrimitive({ id, data }: NodeProps) {
  const d = data as {
    label?: string;
    filename?: string;
    slug?: string;
    status?: string;
    page_count?: number;
    region_count?: number;
    error?: string;
    workspace_slug?: string;
  };
  const status = d.status ?? "ready";
  const cls = STATUS_STYLES[status] ?? STATUS_STYLES.ready;
  const isReady = status === "ready" || status === "found";
  const slug = d.slug;

  const openPdf = useUiStore((s) => s.openPdf);
  const hoveredSourceRef = useUiStore((s) => s.hoveredSourceRef);
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  const { id: workspaceSlug } = useParams<{ id: string }>();

  const [page, setPage] = useState(1);
  const [index, setIndex] = useState<DocumentIndex | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [pageMeta, setPageMeta] = useState<Record<number, PageMeta>>({});
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const [hoveredLocal, setHoveredLocal] = useState<string | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // Fetch index + page metadata once per slug.
  useEffect(() => {
    if (!isReady || !slug) return;
    let cancelled = false;
    documents.index(slug).then((idx) => { if (!cancelled) setIndex(idx); }).catch(() => {});
    fetch(
      `${(import.meta.env.VITE_BACKEND_URL as string | undefined) ?? ""}/api/documents/${slug}/gold-map`,
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((map) => {
        if (cancelled || !map) return;
        const meta = map.pages_meta as Record<string, PageMeta> | undefined;
        if (meta) {
          const numeric: Record<number, PageMeta> = {};
          for (const k of Object.keys(meta)) numeric[Number(k)] = meta[k]!;
          setPageMeta(numeric);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [slug, isReady]);

  // Fetch regions whenever the page changes.
  useEffect(() => {
    if (!isReady || !slug) return;
    let cancelled = false;
    setRegions([]);
    setImgSize(null);
    documents.regions(slug, page).then((rs) => {
      if (!cancelled) setRegions(rs);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [slug, page, isReady]);

  // Phase B: react to a cross-component hover. If something else broadcasts
  // a source_ref pointing into this document, flip to the right page.
  useEffect(() => {
    if (!hoveredSourceRef || !slug || hoveredSourceRef.slug !== slug) return;
    if (hoveredSourceRef.page && hoveredSourceRef.page !== page) {
      setPage(hoveredSourceRef.page);
    }
  }, [hoveredSourceRef, slug, page]);

  const total = index?.document?.page_count ?? d.page_count ?? 0;
  // Prefer explicit page dimensions when the producer exposes them; otherwise
  // derive from the PNG's natural size and the known render DPI (the producer
  // defaults to 150 DPI, so 1 PDF point = 150/72 image pixels).
  const explicitW = pageMeta[page]?.width ?? 0;
  const explicitH = pageMeta[page]?.height ?? 0;
  const derivedW = imgSize ? imgSize.w * POINTS_PER_INCH / RENDER_DPI : 0;
  const derivedH = imgSize ? imgSize.h * POINTS_PER_INCH / RENDER_DPI : 0;
  const pageW = explicitW > 0 ? explicitW : derivedW;
  const pageH = explicitH > 0 ? explicitH : derivedH;
  const canScale = imgSize && pageW > 0 && pageH > 0;
  const coverUrl = isReady && slug ? documents.pageImageUrl(slug, page) : null;

  const externalHighlightId = useMemo(() => {
    if (!hoveredSourceRef || !slug) return null;
    if (hoveredSourceRef.slug !== slug) return null;
    if (hoveredSourceRef.page !== page) return null;
    return hoveredSourceRef.region_id ?? null;
  }, [hoveredSourceRef, slug, page]);

  return (
    <div
      className={`w-80 rounded-lg border-2 text-sm shadow-sm transition ${cls} hover:shadow-md`}
    >
      <Handle type="target" position={Position.Left} />

      {/* Page viewport with overlay.
          Image renders at natural aspect ratio (no maxHeight, no object-fit
          contain), so the wrapper's dimensions exactly equal the rendered
          image's rectangle. The SVG overlay then aligns precisely with the
          image's pixel grid — bbox overlays land where they should.

          `nodrag nopan` on the wrapper opts the whole page-image area out
          of ReactFlow's node-drag and viewport-pan. That way clicks on
          regions go to the region handlers (drag a region → spec node);
          the user can still move the document node by grabbing its body
          or footer below the image. */}
      {coverUrl ? (
        <div className="nodrag nopan relative overflow-hidden rounded-t-md bg-neutral-100">
          <img
            ref={imgRef}
            src={coverUrl}
            alt={d.filename ?? "document"}
            className="block w-full select-none"
            style={{ display: "block", height: "auto" }}
            loading="lazy"
            draggable={false}
            onLoad={(e) => {
              const t = e.currentTarget;
              setImgSize({ w: t.naturalWidth, h: t.naturalHeight });
            }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
          {/* Single-layer region overlay: each region is one absolutely-
              positioned div that handles styling, hover, click AND drag.
              Collapses what used to be three stacked layers (SVG hover,
              vector overlay, transparent drag layer) — those overlapped
              imperfectly and made HTML5 drag flaky. One element per region
              means no hit-test ambiguity. */}
          {canScale && imgSize && slug
            ? regions.map((r, idx) => {
                const bbox = r.bbox;
                if (!bbox || bbox.length < 4) return null;
                // Docling bbox = [left, top, right, bottom] in BOTTOM-LEFT
                // origin (top has larger y than bottom).
                const [l, t, rt, b] = bbox;
                if (l === undefined || b === undefined || rt === undefined || t === undefined) return null;
                const sx = imgSize.w / pageW;
                const sy = imgSize.h / pageH;
                const xpc = (l * sx) / imgSize.w * 100;
                const ypc = ((pageH - t) * sy) / imgSize.h * 100;
                const wpc = ((rt - l) * sx) / imgSize.w * 100;
                const hpc = ((t - b) * sy) / imgSize.h * 100;
                const rid = (r as { id?: string }).id ?? `r${idx}`;
                const isLocal = hoveredLocal === rid;
                const isExternal = externalHighlightId === rid;
                const active = isLocal || isExternal;
                const crops = (r as { crops?: { svg?: string | null } }).crops;
                const svgRel = crops?.svg;
                const overlayUrl = active && svgRel
                  ? `${BACKEND_URL}/api/documents/${slug}/crops/${svgRel}`
                  : null;
                return (
                  <div
                    key={rid}
                    // `nodrag nopan` opts each region out of ReactFlow node-
                    // drag and viewport-pan, so HTML5 drag fires cleanly.
                    className="nodrag nopan absolute cursor-grab active:cursor-grabbing"
                    style={{
                      left: `${xpc}%`,
                      top: `${ypc}%`,
                      width: `${wpc}%`,
                      height: `${hpc}%`,
                      background: active
                        ? "rgba(14, 165, 233, 0.18)"
                        : "rgba(14, 165, 233, 0.04)",
                      outline: active
                        ? "2px solid #0369A1"
                        : "1px solid rgba(14, 165, 233, 0.55)",
                      outlineOffset: "-1px",
                    }}
                    data-region-handle-id={`region:${rid}`}
                    title={r.title ?? r.kind ?? rid}
                    draggable
                    onMouseDown={(e) => e.stopPropagation()}
                    onMouseEnter={() => {
                      setHoveredLocal(rid);
                      setHoveredSourceRef({ slug, page, region_id: rid, bbox });
                    }}
                    onMouseLeave={() => {
                      setHoveredLocal(null);
                      clearHoveredSourceRef();
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      openPdf(slug, {
                        workspaceSlug: workspaceSlug ?? d.workspace_slug,
                        documentNodeId: id,
                        page,
                        highlightRegionId: rid,
                        highlightBbox: bbox,
                      });
                    }}
                    onDragStart={(e) => {
                      e.stopPropagation();
                      const payload = {
                        node_type: "spec",
                        label: r.title ?? r.kind ?? rid,
                        data: {
                          source_doc_slug: slug,
                          source_doc_node_id: id,
                          source_region_id: rid,
                          description: (r as { description?: string }).description,
                          tags: (r as { tags?: string[] }).tags ?? [],
                          source_ref: { kind: "pdf-page-bbox", page, bbox },
                        },
                      };
                      e.dataTransfer.effectAllowed = "copy";
                      e.dataTransfer.setData(
                        "application/x-anchor-node",
                        JSON.stringify(payload),
                      );
                    }}
                  >
                    {overlayUrl ? (
                      <img
                        src={overlayUrl}
                        alt=""
                        className="pointer-events-none absolute inset-0 h-full w-full select-none"
                        loading="lazy"
                        draggable={false}
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : null}
                    {/* Per-region target handle. The handle sits on the
                        region's left edge so an evidence edge from a spec
                        row (whose source handle lives on the spec card's
                        right edge) lands here when the row+region match.
                        Default appearance is a 2px white dot with grey
                        border; hover/active pulls it up to a 6px sky-blue
                        chip via :hover state inherited from the parent. */}
                    <Handle
                      type="target"
                      position={Position.Left}
                      id={`region:${rid}`}
                      className={`!min-w-0 !min-h-0 !border ${
                        active
                          ? "!h-2.5 !w-2.5 !border-sky-700 !bg-sky-400 opacity-100"
                          : "!h-2 !w-2 !border-neutral-400 !bg-white opacity-30"
                      }`}
                      style={{ left: -4, top: "50%" }}
                    />
                  </div>
                );
              })
            : null}
        </div>
      ) : (
        <div className="flex h-24 w-full items-center justify-center rounded-t-md bg-neutral-100 text-3xl text-neutral-400">
          ⌫
        </div>
      )}

      {/* Pagination strip */}
      {total > 1 ? (
        <div className="flex items-center justify-between border-b border-neutral-200 px-2 py-1 text-[11px] text-neutral-600">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.max(1, p - 1));
            }}
            disabled={page <= 1}
            className="rounded border border-neutral-300 px-1.5 py-0.5 hover:bg-neutral-50 disabled:opacity-40"
          >
            ‹
          </button>
          <span className="tabular-nums">
            page {page} / {total}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.min(total, p + 1));
            }}
            disabled={page >= total}
            className="rounded border border-neutral-300 px-1.5 py-0.5 hover:bg-neutral-50 disabled:opacity-40"
          >
            ›
          </button>
        </div>
      ) : null}

      {/* Body label + status + open viewer */}
      <div className="space-y-1 px-3 py-2">
        <div className="text-[10px] uppercase tracking-wide text-neutral-500">
          document
        </div>
        <div className="truncate font-medium text-neutral-900">
          {d.label ?? d.filename ?? "untitled"}
        </div>
        <div className="flex items-center justify-between text-xs text-neutral-500">
          <span>
            {total ? `${total} ${total === 1 ? "page" : "pages"}` : "—"}
            {d.region_count ? ` · ${d.region_count} regions` : null}
          </span>
          {!isReady ? (
            <span className="inline-flex items-center gap-1 rounded border border-current px-1.5 py-0.5 text-[9px] uppercase">
              <span className="block size-1.5 rotate-45 bg-current" />
              {STATUS_LABELS[status] ?? status}
            </span>
          ) : null}
        </div>
        {status === "failed" && d.error ? (
          <div className="truncate text-[10px] text-red-700" title={d.error}>
            {d.error}
          </div>
        ) : null}
        {isReady && slug ? (
          <button
            type="button"
            className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-[11px] font-medium text-neutral-700 hover:bg-neutral-50"
            onClick={(e) => {
              e.stopPropagation();
              openPdf(slug, {
                workspaceSlug: workspaceSlug ?? d.workspace_slug,
                documentNodeId: id,
                page,
              });
            }}
          >
            Open viewer at page {page}
          </button>
        ) : null}
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  );
}

