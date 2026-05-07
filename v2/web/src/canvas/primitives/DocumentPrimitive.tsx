import { useEffect, useMemo, useRef, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

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
          The viewport is constrained by overflow hidden on a max-h wrapper
          if the user wants a smaller node; today we let it scale freely. */}
      {coverUrl ? (
        <div className="relative overflow-hidden rounded-t-md bg-neutral-100">
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
          {canScale && imgSize ? (
            <svg
              className="absolute inset-0 h-full w-full"
              viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
              preserveAspectRatio="none"
            >
              {regions.map((r, idx) => {
                const bbox = r.bbox;
                if (!bbox || bbox.length < 4) return null;
                const [l, b, rt, t] = bbox;
                if (l === undefined || b === undefined || rt === undefined || t === undefined) return null;
                const sx = imgSize.w / pageW;
                const sy = imgSize.h / pageH;
                const x = l * sx;
                const y = (pageH - t) * sy;
                const w = (rt - l) * sx;
                const h = (t - b) * sy;
                const rid = (r as { id?: string }).id ?? `r${idx}`;
                const isLocal = hoveredLocal === rid;
                const isExternal = externalHighlightId === rid;
                const active = isLocal || isExternal;
                return (
                  <g
                    key={rid}
                    style={{ cursor: "grab" }}
                    onMouseEnter={() => {
                      setHoveredLocal(rid);
                      // broadcast outwards too — spec nodes tied to this region
                      // get a reciprocal highlight.
                      if (slug) {
                        setHoveredSourceRef({
                          slug,
                          page,
                          region_id: rid,
                          bbox,
                        });
                      }
                    }}
                    onMouseLeave={() => {
                      setHoveredLocal(null);
                      clearHoveredSourceRef();
                    }}
                    onClick={() => {
                      if (slug) {
                        openPdf(slug, {
                          workspaceSlug: workspaceSlug ?? d.workspace_slug,
                          documentNodeId: id,
                          page,
                          highlightRegionId: rid,
                          highlightBbox: bbox,
                        });
                      }
                    }}
                  >
                    <rect
                      x={x}
                      y={y}
                      width={w}
                      height={h}
                      fill={active ? "rgba(14, 165, 233, 0.28)" : "rgba(14, 165, 233, 0.08)"}
                      stroke={active ? "#0369A1" : "#0EA5E9"}
                      strokeWidth={active ? 4 : 2}
                      strokeDasharray={active ? "0" : "4 3"}
                      vectorEffect="non-scaling-stroke"
                    >
                      <title>{r.title ?? r.kind ?? rid}</title>
                    </rect>
                  </g>
                );
              })}
            </svg>
          ) : null}
          {/* draggable layer — when the user grabs a region's bbox it picks
              up that region's payload as `application/x-anchor-node` */}
          {canScale && imgSize ? (
            <RegionDragLayer
              regions={regions}
              imgSize={imgSize}
              pageW={pageW}
              pageH={pageH}
              page={page}
              docSlug={slug ?? ""}
              docNodeId={id}
            />
          ) : null}
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

/**
 * Transparent layer on top of the page image+SVG that initiates HTML5
 * native drag for whichever region the cursor is over. Separate from the
 * SVG (which can't easily host the dragstart payload that ReactFlow's
 * own onDrop expects) so the SVG handles hover/click and this layer
 * handles drag.
 */
function RegionDragLayer({
  regions,
  imgSize,
  pageW,
  pageH,
  page,
  docSlug,
  docNodeId,
}: {
  regions: Region[];
  imgSize: { w: number; h: number };
  pageW: number;
  pageH: number;
  page: number;
  docSlug: string;
  docNodeId: string;
}) {
  return (
    <div className="absolute inset-0 pointer-events-none">
      {regions.map((r, idx) => {
        const bbox = r.bbox;
        if (!bbox || bbox.length < 4) return null;
        const [l, b, rt, t] = bbox;
        if (l === undefined || b === undefined || rt === undefined || t === undefined) return null;
        const sx = imgSize.w / pageW;
        const sy = imgSize.h / pageH;
        const x = (l * sx) / imgSize.w * 100;
        const y = ((pageH - t) * sy) / imgSize.h * 100;
        const w = ((rt - l) * sx) / imgSize.w * 100;
        const h = ((t - b) * sy) / imgSize.h * 100;
        const rid = (r as { id?: string }).id ?? `r${idx}`;
        return (
          <div
            key={rid}
            className="absolute pointer-events-auto cursor-grab active:cursor-grabbing"
            style={{ left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` }}
            draggable
            onDragStart={(e) => {
              e.stopPropagation();
              const payload = {
                node_type: "spec",
                label: r.title ?? r.kind ?? rid,
                data: {
                  source_doc_slug: docSlug,
                  source_doc_node_id: docNodeId,
                  source_region_id: rid,
                  description: (r as { description?: string }).description,
                  tags: (r as { tags?: string[] }).tags ?? [],
                  source_ref: {
                    kind: "pdf-page-bbox",
                    page,
                    bbox,
                  },
                },
              };
              e.dataTransfer.effectAllowed = "copy";
              e.dataTransfer.setData(
                "application/x-anchor-node",
                JSON.stringify(payload),
              );
            }}
          />
        );
      })}
    </div>
  );
}
