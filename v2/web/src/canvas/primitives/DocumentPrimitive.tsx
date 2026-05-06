import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { documents } from "@/api/documents";
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
  const openPdf = useUiStore((s) => s.openPdf);
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const cls = STATUS_STYLES[status] ?? STATUS_STYLES.ready;
  const isReady = status === "ready" || status === "found";
  const coverUrl = isReady && d.slug ? documents.pageImageUrl(d.slug, 1) : null;

  // Double-click handling lives in CanvasGraph.onNodeDoubleClick because
  // ReactFlow intercepts dblclick at the node level. Keep this component
  // purely presentational.
  return (
    <div
      className={`w-56 cursor-pointer rounded-lg border-2 text-sm shadow-sm transition ${cls} hover:shadow-md`}
    >
      <Handle type="target" position={Position.Left} />
      {coverUrl ? (
        <div className="overflow-hidden rounded-t-md bg-neutral-100">
          <img
            src={coverUrl}
            alt={d.filename ?? "document"}
            className="block h-32 w-full object-cover object-top"
            loading="lazy"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      ) : (
        <div className="flex h-24 w-full items-center justify-center rounded-t-md bg-neutral-100 text-3xl text-neutral-400">
          ⌫
        </div>
      )}
      <div className="space-y-1 px-3 py-2">
        <div className="text-[10px] uppercase tracking-wide text-neutral-500">
          document
        </div>
        <div className="truncate font-medium text-neutral-900">
          {d.label ?? d.filename ?? "untitled"}
        </div>
        <div className="flex items-center justify-between text-xs text-neutral-500">
          <span>
            {d.page_count
              ? `${d.page_count} ${d.page_count === 1 ? "page" : "pages"}`
              : "—"}
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
        {isReady && d.slug ? (
          <button
            type="button"
            className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-[11px] font-medium text-neutral-700 hover:bg-neutral-50"
            onClick={(e) => {
              e.stopPropagation();
              if (d.slug) openPdf(d.slug, {
                workspaceSlug: workspaceSlug ?? d.workspace_slug,
                documentNodeId: id,
              });
            }}
          >
            Open viewer
          </button>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
