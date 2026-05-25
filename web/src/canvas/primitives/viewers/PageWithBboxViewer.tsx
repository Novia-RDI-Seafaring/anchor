import { useEffect, useState } from "react";

import { canvases } from "@/api/canvases";
import { documents, type DocumentIndex, type Region } from "@/api/documents";
import { useUiStore } from "@/stores/uiStore";

/**
 * Modal PDF viewer.
 *
 * Renders the page image plus an SVG overlay drawing each region's bbox
 * from gold regions, scaled to the rendered image. Click a region to focus
 * it; double-click to lock and show metadata.
 *
 * Bbox coordinates from gold regions arrive in Docling's BOTTOMLEFT
 * (PDF user-space) origin. We convert to image (top-left) coordinates
 * using the page's width/height in points from pages.meta.json.
 */

type PageMeta = { width: number; height: number };

const RENDER_DPI = 150;
const POINTS_PER_INCH = 72;

export function PageWithBboxViewer() {
  const viewer = useUiStore((s) => s.pdfViewer);
  const close = useUiStore((s) => s.closePdf);
  const setPage = useUiStore((s) => s.setPdfPage);

  const [index, setIndex] = useState<DocumentIndex | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [pageMeta, setPageMeta] = useState<Record<number, PageMeta>>({});
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const [activeRegion, setActiveRegion] = useState<string | null>(null);
  const [sending, setSending] = useState<string | null>(null);

  async function sendRegionToCanvas(region: Region & { description?: string }) {
    if (!viewer?.workspaceSlug || !viewer?.documentNodeId) return;
    const rid = (region as { id?: string }).id ?? `r${Date.now()}`;
    setSending(rid);
    try {
      const newNode = await canvases.addNode(viewer.workspaceSlug, {
        node_type: "spec",
        label: region.title ?? region.kind ?? "spec",
        x: 600 + Math.random() * 80,
        y: 200 + Math.random() * 80,
        data: {
          source_doc_slug: viewer.slug,
          source_region_id: rid,
          description: region.description,
          tags: (region as { tags?: string[] }).tags ?? [],
          source_ref: {
            kind: "pdf-page-bbox",
            page: region.page ?? viewer.page,
            bbox: region.bbox,
          },
        },
      }) as { event?: { payload?: { id?: string } } };
      const newNodeId = newNode?.event?.payload?.id;
      if (newNodeId) {
        await canvases.addEdge(viewer.workspaceSlug, {
          source: newNodeId,
          target: viewer.documentNodeId,
          label: `page ${region.page ?? viewer.page}`,
          edge_type: "anchored",
          data: {
            source_ref: {
              kind: "pdf-page-bbox",
              page: region.page ?? viewer.page,
              bbox: region.bbox,
            },
          },
        });
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("send region to canvas failed", err);
    } finally {
      setSending(null);
    }
  }

  useEffect(() => {
    if (!viewer) return;
    let cancel = false;
    setIndex(null);
    setRegions([]);
    setActiveRegion(null);
    documents.index(viewer.slug).then((idx) => {
      if (!cancel) setIndex(idx);
    }).catch(() => {});
    fetch(`${(import.meta.env.VITE_BACKEND_URL as string | undefined) ?? ""}/api/documents/${viewer.slug}/gold-map`)
      .then((r) => r.ok ? r.json() : null)
      .then((map) => {
        if (cancel || !map) return;
        const meta = map.pages_meta as Record<string, PageMeta> | undefined;
        if (meta) {
          const numeric: Record<number, PageMeta> = {};
          for (const k of Object.keys(meta)) numeric[Number(k)] = meta[k]!;
          setPageMeta(numeric);
        }
      })
      .catch(() => {});
    return () => {
      cancel = true;
    };
  }, [viewer?.slug]);

  useEffect(() => {
    if (!viewer) return;
    let cancel = false;
    setRegions([]);
    setImgSize(null);
    // Preserve activeRegion when openPdf supplied a highlightRegionId; that
    // way the viewer opens already focused on the deep-link region.
    setActiveRegion(viewer.highlightRegionId ?? null);
    documents.regions(viewer.slug, viewer.page).then((rs) => {
      if (!cancel) setRegions(rs);
    }).catch(() => setRegions([]));
    return () => {
      cancel = true;
    };
  }, [viewer?.slug, viewer?.page, viewer?.highlightRegionId]);

  useEffect(() => {
    if (!viewer) return;
    function onKey(e: KeyboardEvent) {
      if (!viewer) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight" && index?.document && viewer.page < index.document.page_count) {
        setPage(viewer.page + 1);
      } else if (e.key === "ArrowLeft" && viewer.page > 1) {
        setPage(viewer.page - 1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewer, index, close, setPage]);

  if (!viewer) return null;

  const total = index?.document?.page_count ?? 0;
  const explicitW = pageMeta[viewer.page]?.width ?? 0;
  const explicitH = pageMeta[viewer.page]?.height ?? 0;
  const derivedW = imgSize ? imgSize.w * POINTS_PER_INCH / RENDER_DPI : 0;
  const derivedH = imgSize ? imgSize.h * POINTS_PER_INCH / RENDER_DPI : 0;
  const pageW = explicitW > 0 ? explicitW : derivedW;
  const pageH = explicitH > 0 ? explicitH : derivedH;
  const canScale = imgSize && pageW > 0 && pageH > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur-sm"
    >
      <header className="flex items-center justify-between border-b border-white/10 px-4 py-2 text-white">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={close}
            className="rounded px-2 py-1 text-sm hover:bg-white/10"
          >
            ✕ Close
          </button>
          <div className="text-sm opacity-80">
            {index?.document?.title ?? viewer.slug}
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => setPage(Math.max(1, viewer.page - 1))}
            disabled={viewer.page <= 1}
            className="rounded border border-white/20 px-2 py-1 disabled:opacity-30"
          >
            ‹ Prev
          </button>
          <span className="tabular-nums">
            {viewer.page} / {total || "?"}
          </span>
          <button
            type="button"
            onClick={() => setPage(Math.min(total || viewer.page, viewer.page + 1))}
            disabled={total > 0 && viewer.page >= total}
            className="rounded border border-white/20 px-2 py-1 disabled:opacity-30"
          >
            Next ›
          </button>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <main className="relative flex flex-1 items-center justify-center overflow-auto p-6">
          <div className="relative">
            <img
              src={documents.pageImageUrl(viewer.slug, viewer.page)}
              alt={`${viewer.slug} page ${viewer.page}`}
              className="max-h-[calc(100vh-7rem)] w-auto rounded shadow-lg"
              onLoad={(e) => {
                const t = e.currentTarget;
                setImgSize({ w: t.naturalWidth, h: t.naturalHeight });
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
                  // Docling: BOTTOMLEFT origin (left, bottom, right, top in points).
                  // Image: TOPLEFT origin (pixels). Convert.
                  // Docling bbox = [left, top, right, bottom] in BOTTOM-LEFT
                  // origin (top has larger y than bottom).
                  const [l, t, rt, b] = bbox;
                  if (l === undefined || b === undefined || rt === undefined || t === undefined) return null;
                  const sx = imgSize.w / pageW;
                  const sy = imgSize.h / pageH;
                  const x = l * sx;
                  const y = (pageH - t) * sy;
                  const w = (rt - l) * sx;
                  const h = (t - b) * sy;
                  const rid = r.id ?? `r${idx}`;
                  const isActive = activeRegion === rid;
                  return (
                    <rect
                      key={rid}
                      x={x}
                      y={y}
                      width={w}
                      height={h}
                      fill={isActive ? "rgba(14, 165, 233, 0.30)" : "rgba(14, 165, 233, 0.10)"}
                      stroke={isActive ? "#0369A1" : "#0EA5E9"}
                      strokeWidth={isActive ? 3 : 1.6}
                      strokeDasharray={isActive ? "0" : "4 3"}
                      vectorEffect="non-scaling-stroke"
                      style={{ cursor: "pointer" }}
                      onClick={() => setActiveRegion(rid)}
                    >
                      <title>{r.title ?? r.kind ?? rid}</title>
                    </rect>
                  );
                })}
                {/* Deep-zoom emphasis: when openPdf was called with a
                    specific highlightBbox AND that bbox differs from the
                    active region's bbox, draw an inner emphasis box on the
                    sub-region (e.g. a row inside a spec_block table). */}
                {(() => {
                  const sub = viewer.highlightBbox;
                  if (!sub || sub.length < 4) return null;
                  const active = regions.find(
                    (rr) => ((rr as { id?: string }).id ?? "") === activeRegion,
                  );
                  // If the highlight bbox matches the parent region bbox,
                  // skip the inner emphasis (the parent rect already covers it).
                  const parent = active?.bbox;
                  if (parent && parent.length === 4 && parent.every((v, i) => v === sub[i])) return null;
                  // sub = [left, top, right, bottom] BL origin (top > bottom).
                  const [l, t, rt, b] = sub as [number, number, number, number];
                  if (l === undefined || b === undefined || rt === undefined || t === undefined) return null;
                  const sx = imgSize.w / pageW;
                  const sy = imgSize.h / pageH;
                  const x = l * sx;
                  const y = (pageH - t) * sy;
                  const w = (rt - l) * sx;
                  const h = (t - b) * sy;
                  return (
                    <rect
                      x={x}
                      y={y}
                      width={w}
                      height={h}
                      fill="rgba(244, 114, 22, 0.35)"
                      stroke="#EA580C"
                      strokeWidth={3.5}
                      vectorEffect="non-scaling-stroke"
                    >
                      <title>highlight target</title>
                    </rect>
                  );
                })()}
              </svg>
            ) : null}
          </div>
        </main>
        <aside className="w-72 overflow-y-auto border-l border-white/10 bg-neutral-900/80 p-3 text-sm text-white">
          <div className="mb-2 text-xs uppercase tracking-wide opacity-60">
            Page {viewer.page} regions ({regions.length})
          </div>
          {regions.length === 0 ? (
            <div className="text-xs opacity-60">No regions on this page.</div>
          ) : (
            <ul className="space-y-1">
              {regions.map((r, idx) => {
                const rid = r.id ?? `r${idx}`;
                return (
                  <li key={rid}>
                    <div
                      className={`rounded px-2 py-1 text-xs transition ${
                        activeRegion === rid
                          ? "bg-sky-500/30 ring-1 ring-sky-400"
                          : "hover:bg-white/5"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => setActiveRegion(rid)}
                        className="block w-full text-left"
                      >
                        <div className="font-medium opacity-90">
                          {r.title ?? r.kind ?? rid}
                        </div>
                        {r.kind ? (
                          <div className="text-[10px] uppercase opacity-50">
                            {r.kind}
                          </div>
                        ) : null}
                        {r.description ? (
                          <div className="mt-1 line-clamp-2 text-[11px] opacity-70">
                            {r.description}
                          </div>
                        ) : null}
                      </button>
                      {viewer.workspaceSlug && viewer.documentNodeId ? (
                        <button
                          type="button"
                          onClick={() => sendRegionToCanvas(r)}
                          disabled={sending === rid}
                          className="mt-2 w-full rounded border border-sky-400/40 bg-sky-500/10 px-2 py-1 text-[10px] uppercase tracking-wide hover:bg-sky-500/20 disabled:opacity-50"
                        >
                          {sending === rid ? "adding…" : "→ send to canvas"}
                        </button>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}
