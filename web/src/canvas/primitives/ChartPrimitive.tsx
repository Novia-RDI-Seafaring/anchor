import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import type React from "react";
import { useMemo } from "react";

import { useLiveResize } from "@/canvas/useLiveResize";
import { useUiStore } from "@/stores/uiStore";

/**
 * ChartPrimitive — renders a region whose OIP `ui_hints.renders` token is
 * `chart`. It is producer-agnostic: any producer that emits a region with
 * `content.data` shaped like the OIP `chart` token draws here, the same way
 * `TablePrimitive` serves the `table` token. The chart digitizer
 * (graph-data-extractor) is the first such producer; a spreadsheet importer
 * or a log analyser would reuse this node unchanged.
 *
 * Data contract (the `chart` token payload, carried on `data.chart` or
 * directly on `data`):
 *
 *   { x_label?, y_label?, x_scale?: "linear"|"log", y_scale?: ...,
 *     series: [{ label, points: [[x, y], ...] }] }
 *
 * Provenance: when the region kept its source `source_ref` (a derived
 * region inherits its parent's), the footer chip opens the PDF at that
 * page and highlights the bbox — the same evidence contract every other
 * primitive honours.
 */

type Point = [number, number];
type Series = { label: string; points: Point[]; color?: string };
type ChartData = {
  x_label?: string;
  y_label?: string;
  x_scale?: "linear" | "log";
  y_scale?: "linear" | "log";
  series: Series[];
};
type SourceRef = { kind?: string; slug?: string; page?: number; region_id?: string; bbox?: number[] };

// Colour-blind-safe-ish categorical palette; series without an explicit
// colour cycle through it.
const PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];

const MARGIN = { top: 8, right: 10, bottom: 26, left: 34 };

function project(v: number, scale: "linear" | "log" | undefined): number {
  return scale === "log" ? Math.log10(Math.max(v, 1e-9)) : v;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (!isFinite(min) || !isFinite(max) || min === max) return [min];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + i * step);
}

export function ChartPrimitive({ id: _id, data, selected }: NodeProps) {
  const d = (data ?? {}) as {
    label?: string;
    chart?: ChartData;
    data?: ChartData;
    series?: Series[];
    source_ref?: SourceRef;
    width?: number;
    height?: number;
  };
  const chart = useMemo<ChartData | undefined>(
    () => d.chart ?? d.data ?? (d.series ? { series: d.series } : undefined),
    [d.chart, d.data, d.series],
  );

  const openPdf = useUiStore((s) => s.openPdf);
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);

  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width ?? 340,
    d.height ?? 260,
  );
  const W = liveW ?? 340;
  const H = liveH ?? 260;
  const plotW = W - MARGIN.left - MARGIN.right;
  const plotH = H - MARGIN.top - MARGIN.bottom - 40; // header + footer reserve

  const geom = useMemo(() => {
    const series = (chart?.series ?? []).filter((s) => s.points?.length);
    if (!series.length) return null;
    const xs: number[] = [];
    const ys: number[] = [];
    for (const s of series) for (const [x, y] of s.points) {
      xs.push(project(x, chart?.x_scale));
      ys.push(project(y, chart?.y_scale));
    }
    const xmin = Math.min(...xs), xmax = Math.max(...xs);
    const ymin = Math.min(...ys), ymax = Math.max(...ys);
    const sx = (x: number) =>
      MARGIN.left + ((project(x, chart?.x_scale) - xmin) / (xmax - xmin || 1)) * plotW;
    const sy = (y: number) =>
      MARGIN.top + plotH - ((project(y, chart?.y_scale) - ymin) / (ymax - ymin || 1)) * plotH;
    return { series, xmin, xmax, ymin, ymax, sx, sy };
  }, [chart, plotW, plotH]);

  const ref = d.source_ref;
  const hasProv = !!(ref?.slug && ref?.page != null);
  const broadcastHover = () => {
    if (hasProv) setHoveredSourceRef({ slug: ref!.slug!, page: ref!.page!, region_id: ref!.region_id, bbox: ref!.bbox });
  };

  return (
    <div
      className={`relative rounded-lg border ${selected ? "cursor-move border-neutral-500" : "cursor-pointer border-neutral-400"} bg-white text-sm shadow-sm`}
      style={{ width: W, height: H }}
      onMouseEnter={broadcastHover}
      onMouseLeave={clearHoveredSourceRef}
    >
      <NodeResizer isVisible={selected ?? false} minWidth={240} minHeight={180} {...resizeHandlers} />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />

      <div className="truncate px-3 py-1.5 text-[13px] font-semibold text-neutral-800">
        {d.label || "Chart"}
      </div>

      {geom ? (
        <svg width={W} height={H - 40} className="block" role="img" aria-label={d.label || "chart"}>
          {/* axes */}
          <line x1={MARGIN.left} y1={MARGIN.top} x2={MARGIN.left} y2={MARGIN.top + plotH} stroke="#9ca3af" strokeWidth={1} />
          <line x1={MARGIN.left} y1={MARGIN.top + plotH} x2={MARGIN.left + plotW} y2={MARGIN.top + plotH} stroke="#9ca3af" strokeWidth={1} />
          {/* y ticks */}
          {niceTicks(geom.ymin, geom.ymax).map((t, i) => {
            const yv = chart?.y_scale === "log" ? Math.pow(10, t) : t;
            const py = MARGIN.top + plotH - ((t - geom.ymin) / (geom.ymax - geom.ymin || 1)) * plotH;
            return (
              <g key={`y${i}`}>
                <line x1={MARGIN.left - 3} y1={py} x2={MARGIN.left + plotW} y2={py} stroke="#f1f5f9" strokeWidth={1} />
                <text x={MARGIN.left - 5} y={py + 3} textAnchor="end" fontSize={8} fill="#64748b">
                  {Number(yv.toPrecision(3))}
                </text>
              </g>
            );
          })}
          {/* x ticks */}
          {niceTicks(geom.xmin, geom.xmax).map((t, i) => {
            const xv = chart?.x_scale === "log" ? Math.pow(10, t) : t;
            const px = MARGIN.left + ((t - geom.xmin) / (geom.xmax - geom.xmin || 1)) * plotW;
            return (
              <text key={`x${i}`} x={px} y={MARGIN.top + plotH + 12} textAnchor="middle" fontSize={8} fill="#64748b">
                {Number(xv.toPrecision(3))}
              </text>
            );
          })}
          {/* axis labels */}
          {chart?.x_label && (
            <text x={MARGIN.left + plotW / 2} y={H - 40 - 2} textAnchor="middle" fontSize={9} fill="#475569">{chart.x_label}</text>
          )}
          {chart?.y_label && (
            <text transform={`translate(9 ${MARGIN.top + plotH / 2}) rotate(-90)`} textAnchor="middle" fontSize={9} fill="#475569">{chart.y_label}</text>
          )}
          {/* series polylines */}
          {geom.series.map((s, i) => (
            <polyline
              key={s.label || i}
              fill="none"
              stroke={s.color ?? PALETTE[i % PALETTE.length]}
              strokeWidth={1.6}
              points={s.points.map(([x, y]) => `${geom.sx(x)},${geom.sy(y)}`).join(" ")}
            />
          ))}
        </svg>
      ) : (
        <div className="px-3 py-6 text-center text-xs text-neutral-400">no series data</div>
      )}

      {/* legend + provenance footer */}
      <div className="flex items-center justify-between gap-2 px-3 py-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 overflow-hidden">
          {(geom?.series ?? []).slice(0, 4).map((s, i) => (
            <span key={s.label || i} className="flex items-center gap-1 text-[10px] text-neutral-600">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.color ?? PALETTE[i % PALETTE.length] }} />
              <span className="max-w-[80px] truncate">{s.label}</span>
            </span>
          ))}
        </div>
        {hasProv && (
          <button
            type="button"
            className="nodrag nopan shrink-0 rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600 hover:bg-neutral-200"
            onMouseDown={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              openPdf(ref!.slug!, { page: ref!.page, highlightRegionId: ref!.region_id, highlightBbox: ref!.bbox });
            }}
            title={`Open source · page ${ref!.page}`}
          >
            p.{ref!.page}
          </button>
        )}
      </div>
    </div>
  );
}
