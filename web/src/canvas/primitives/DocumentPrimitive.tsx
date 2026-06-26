import { useEffect, useMemo, useRef, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { BACKEND_URL } from "@/api/client";
import { documents, type DocumentIndex, type Region } from "@/api/documents";
import { bboxToImageRect, sameBbox } from "@/lib/bbox";
import { useUiStore } from "@/stores/uiStore";

const STATUS_STYLES: Record<string, string> = {
  pending: "border-amber-400 bg-amber-50",
  // Harness-ingest projects: the dropped doc is waiting for the agent to run
  // the ingest (issue #148). Same amber "needs attention" cue as queued.
  awaiting_agent: "border-amber-400 bg-amber-50",
  ingesting: "border-blue-400 bg-blue-50",
  searching: "border-blue-400 bg-blue-50",
  found: "border-emerald-400 bg-emerald-50",
  failed: "border-red-400 bg-red-50",
  ready: "border-neutral-300 bg-white",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "queued",
  awaiting_agent: "awaiting agent",
  ingesting: "ingesting",
  searching: "ingesting",
  found: "ready",
  failed: "failed",
  ready: "ready",
};

function formatElapsed(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0s";
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  if (minutes <= 0) return `${secs}s`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours <= 0) return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
  return `${hours}h ${mins.toString().padStart(2, "0")}m`;
}

function numericSeconds(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

type PageMeta = { width: number; height: number };
type RegionHighlight = { regionId?: string; bbox?: number[] };

// Default DPI used by anchor_pdfs when rendering page PNGs. Matches
// AnchorConfig.dpi. If the producer is reconfigured to a different DPI,
// gold-map should expose it explicitly; for now we assume the default.
const RENDER_DPI = 150;
const POINTS_PER_INCH = 72;

function matchesExternalHighlight(
  highlight: RegionHighlight | null,
  rid: string,
  bbox: number[],
): boolean {
  if (!highlight) return false;
  if (highlight.bbox && !sameBbox(highlight.bbox, bbox)) return false;
  if (highlight.regionId) return highlight.regionId === rid;
  return sameBbox(highlight.bbox, bbox);
}

/**
 * DocumentPrimitive: a paginated document viewport on the canvas.
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
    embedded_count?: number;
    ingest_progress?: number;
    ingest_stage?: string;
    ingest_stage_label?: string;
    ingest_current?: number;
    ingest_total?: number;
    ingest_started_at?: number;
    ingest_updated_at?: number;
    ingest_finished_at?: number;
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
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (isReady) return;
    const timer = window.setInterval(() => setNowSeconds(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [isReady]);

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
  const ingestProgress = typeof d.ingest_progress === "number"
    ? Math.max(0, Math.min(100, Math.round(d.ingest_progress)))
    : status === "pending"
      ? 0
      : (status === "ingesting" || status === "searching")
        ? 1
        : null;
  const ingestLabel = d.ingest_stage_label
    ?? (d.ingest_stage ? d.ingest_stage.replaceAll("_", " ") : STATUS_LABELS[status] ?? status);
  const ingestDetail = d.ingest_total && d.ingest_total > 1
    ? `${d.ingest_current ?? 0}/${d.ingest_total}`
    : null;
  const ingestStartedAt = numericSeconds(d.ingest_started_at);
  const ingestFinishedAt = numericSeconds(d.ingest_finished_at);
  const elapsedSeconds = ingestStartedAt === null
    ? null
    : Math.max(0, (ingestFinishedAt ?? nowSeconds) - ingestStartedAt);
  const elapsedLabel = elapsedSeconds === null
    ? status === "pending" ? "waiting" : "running"
    : `elapsed ${formatElapsed(elapsedSeconds)}`;

  const externalHighlight = useMemo<RegionHighlight | null>(() => {
    if (!hoveredSourceRef || !slug) return null;
    if (hoveredSourceRef.slug !== slug) return null;
    if (hoveredSourceRef.page !== page) return null;
    return { regionId: hoveredSourceRef.region_id, bbox: hoveredSourceRef.bbox };
  }, [hoveredSourceRef, slug, page]);

  return (
    <div
      className={`w-80 rounded-lg border-2 text-sm shadow-sm transition ${cls} hover:shadow-md`}
    >
      <Handle type="target" position={Position.Left} className="canvas-node-socket" />

      {/* Page viewport with overlay.
          Image renders at natural aspect ratio (no maxHeight, no object-fit
          contain), so the wrapper's dimensions exactly equal the rendered
          image's rectangle. The SVG overlay then aligns precisely with the
          image's pixel grid, so bbox overlays land where they should.

          The wrapper itself does NOT opt out of node-drag. That way the
          user can grab the empty space between regions (or the image
          background) to move the whole document node. Each region
          rendered inside this wrapper has its own `nodrag` so the
          drag-out-to-spec gesture still wins on a region. The <img>
          element is `nodrag` so pointer events on the cover image don't
          fire region drags, but they still propagate to the wrapper for
          node move. */}
      {coverUrl ? (
        <div className="relative overflow-hidden rounded-t-md bg-neutral-100 cursor-move">
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
              vector overlay, transparent drag layer). Those overlapped
              imperfectly and made HTML5 drag flaky. One element per region
              means no hit-test ambiguity. */}
          {canScale && imgSize && slug
            ? regions.map((r, idx) => {
                // Order-independent bbox → image rect (see lib/bbox). The
                // gold extractor's 4-tuple ordering is not guaranteed, so we
                // never assume bbox[1] is the top edge.
                const rect = bboxToImageRect(r.bbox, pageW, pageH, imgSize.w, imgSize.h);
                if (!rect) return null;
                const xpc = (rect.x / imgSize.w) * 100;
                const ypc = (rect.y / imgSize.h) * 100;
                const wpc = (rect.w / imgSize.w) * 100;
                const hpc = (rect.h / imgSize.h) * 100;
                // rect is non-null only when bbox has ≥4 valid numbers.
                const bbox = r.bbox as number[];
                const rid = (r as { id?: string }).id ?? `r${idx}`;
                const isLocal = hoveredLocal === rid;
                const isExternal = matchesExternalHighlight(externalHighlight, rid, bbox);
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
                        ? "rgba(16, 185, 129, 0.18)"
                        : "transparent",
                      outline: active
                        ? "2px solid #059669"
                        : "1px solid transparent",
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
                    onDoubleClick={(e) => e.stopPropagation()}
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
                          crops: r.crops,
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
                      className={`canvas-region-socket !min-w-0 !min-h-0 !border ${
                        active
                          ? "!h-2.5 !w-2.5 !border-emerald-700 !bg-emerald-400 opacity-100"
                          : "!h-2 !w-2 !border-neutral-400 !bg-white opacity-0"
                      }`}
                      style={{ left: -4, top: "50%" }}
                    />
                  </div>
                );
              })
            : null}
          {canScale && imgSize && externalHighlight?.bbox
            ? (() => {
                const parent = externalHighlight.regionId
                  ? regions.find((r, idx) => ((r as { id?: string }).id ?? `r${idx}`) === externalHighlight.regionId)
                  : undefined;
                if (parent?.bbox && sameBbox(externalHighlight.bbox, parent.bbox)) return null;
                const rect = bboxToImageRect(externalHighlight.bbox, pageW, pageH, imgSize.w, imgSize.h);
                if (!rect) return null;
                const xpc = (rect.x / imgSize.w) * 100;
                const ypc = (rect.y / imgSize.h) * 100;
                const wpc = (rect.w / imgSize.w) * 100;
                const hpc = (rect.h / imgSize.h) * 100;
                return (
                  <div
                    className="pointer-events-none absolute"
                    style={{
                      left: `${xpc}%`,
                      top: `${ypc}%`,
                      width: `${wpc}%`,
                      height: `${hpc}%`,
                      background: "rgba(16, 185, 129, 0.22)",
                      outline: "2px solid #059669",
                      outlineOffset: "-1px",
                    }}
                  />
                );
              })()
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
            className="nodrag nopan rounded border border-neutral-300 px-1.5 py-0.5 hover:bg-neutral-50 disabled:opacity-40"
            disabled={page <= 1}
            // stopPropagation on BOTH click and double-click: a fast
            // double-tap on the arrow would otherwise reach ReactFlow's
            // node-level onDoubleClick and open the PDF viewer (#184). The
            // click handler alone does not stop the separate dblclick event.
            onMouseDown={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.max(1, p - 1));
            }}
          >
            ‹
          </button>
          <span className="tabular-nums">
            page {page} / {total}
          </span>
          <button
            type="button"
            className="nodrag nopan rounded border border-neutral-300 px-1.5 py-0.5 hover:bg-neutral-50 disabled:opacity-40"
            disabled={page >= total}
            onMouseDown={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              setPage((p) => Math.min(total, p + 1));
            }}
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
            {total ? `${total} ${total === 1 ? "page" : "pages"}` : "-"}
            {d.region_count ? ` · ${d.region_count} regions` : null}
            {d.embedded_count ? ` · ${d.embedded_count} embedded` : null}
          </span>
          {!isReady ? (
            <span className="inline-flex items-center gap-1 rounded border border-current px-1.5 py-0.5 text-[9px] uppercase">
              <span className="block size-1.5 rotate-45 bg-current" />
              {STATUS_LABELS[status] ?? status}
            </span>
          ) : null}
        </div>
        {!isReady && ingestProgress !== null ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2 text-[10px] text-neutral-600">
              <span className="truncate capitalize">{ingestLabel}</span>
              <span className="shrink-0 tabular-nums">
                {ingestProgress}% · {elapsedLabel}
                {ingestDetail ? ` · ${ingestDetail} pages` : null}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-neutral-200">
              <div
                className={status === "failed" ? "h-full bg-red-500" : "h-full bg-sky-500"}
                style={{ width: `${ingestProgress}%` }}
              />
            </div>
          </div>
        ) : null}
        {status === "failed" && d.error ? (
          <div className="truncate text-[10px] text-red-700" title={d.error}>
            {d.error}
          </div>
        ) : null}
        {isReady && slug ? (
          <button
            type="button"
            className="nodrag nopan mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-[11px] font-medium text-neutral-700 hover:bg-neutral-50"
            onMouseDown={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
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

      <Handle type="source" position={Position.Right} className="canvas-node-socket" />
    </div>
  );
}

