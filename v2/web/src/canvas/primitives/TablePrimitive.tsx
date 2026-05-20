import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { documents } from "@/api/documents";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

type Row = { key: string; value: string; source_ref?: { page: number; bbox?: number[] } };

type SourceRef = { kind?: string; page?: number; bbox?: number[] };

export function TablePrimitive({ data }: NodeProps) {
  const d = data as {
    label?: string;
    rows?: Row[];
    description?: string;
    tags?: string[];
    source_doc_slug?: string;
    source_doc_node_id?: string;
    source_region_id?: string;
    source_ref?: SourceRef;
    dashed?: boolean;
  };
  const rows = d.rows ?? [];
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  const openPdf = useUiStore((s) => s.openPdf);
  const { id: workspaceSlug } = useParams<{ id: string }>();

  const broadcastHover = () => {
    if (d.source_doc_slug && d.source_ref?.page) {
      setHoveredSourceRef({
        slug: d.source_doc_slug,
        page: d.source_ref.page,
        region_id: d.source_region_id,
        bbox: d.source_ref.bbox,
      });
    }
  };

  // Click → open the PDF viewer at this spec's source page with the bbox
  // highlighted. The viewer also wants a documentNodeId so its "send region
  // to canvas" sidebar can wire evidence edges back to the same source
  // document; resolve it either from the spec's stored source_doc_node_id
  // or, as a fallback for older nodes that don't carry it, by looking up
  // the matching document node in the canvas store by slug.
  const openSource = () => {
    if (!d.source_doc_slug || !d.source_ref?.page) return;
    let docNodeId = d.source_doc_node_id;
    if (!docNodeId) {
      const nodes = useCanvasStore.getState().nodes;
      for (const n of Object.values(nodes)) {
        const nd = n.data as { slug?: string } | undefined;
        if (n.node_type === "document" && nd?.slug === d.source_doc_slug) {
          docNodeId = n.id;
          break;
        }
      }
    }
    openPdf(d.source_doc_slug, {
      page: d.source_ref.page,
      workspaceSlug,
      documentNodeId: docNodeId,
      highlightRegionId: d.source_region_id,
      highlightBbox: d.source_ref.bbox,
    });
  };

  const cropUrl =
    d.source_doc_slug && d.source_region_id && d.source_ref?.page
      ? `${(import.meta.env.VITE_BACKEND_URL as string | undefined) ?? ""}/api/documents/${d.source_doc_slug}/crops/${d.source_ref.page}/${d.source_region_id}.png`
      : null;

  const canOpen = Boolean(d.source_doc_slug && d.source_ref?.page);

  return (
    <div
      className={`w-72 rounded-lg border ${borderStyle} border-neutral-400 bg-white text-sm shadow-sm`}
      onMouseEnter={broadcastHover}
      onMouseLeave={clearHoveredSourceRef}
    >
      <Handle type="target" position={Position.Left} />
      <div
        className={`flex items-center justify-between border-b border-neutral-200 px-3 py-2 gap-2 ${
          canOpen ? "nodrag nopan cursor-pointer hover:bg-sky-50/60" : ""
        }`}
        onClick={() => {
          if (canOpen) openSource();
        }}
        title={canOpen ? `Open page ${d.source_ref?.page} in viewer` : undefined}
      >
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">spec</div>
          <div className="truncate font-medium text-neutral-900">
            {d.label ?? "spec"}
          </div>
        </div>
        {d.source_ref?.page ? (
          <button
            type="button"
            className="nodrag nopan shrink-0 rounded border border-sky-300 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 hover:bg-sky-100"
            title={`Open page ${d.source_ref.page} in viewer`}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              // Stop bubbling here so the surrounding header onClick (which
              // would fire `openSource` a second time) doesn't double-trigger.
              e.stopPropagation();
              openSource();
            }}
          >
            p{d.source_ref.page}
          </button>
        ) : null}
      </div>

      {cropUrl ? (
        <div
          className={`border-b border-neutral-200 bg-neutral-50 ${
            canOpen ? "nodrag nopan cursor-pointer" : ""
          }`}
          onClick={() => {
            if (canOpen) openSource();
          }}
          title={canOpen ? `Open page ${d.source_ref?.page} in viewer` : undefined}
        >
          <img
            src={cropUrl}
            alt={d.label ?? "region"}
            className="block max-h-32 w-full object-contain"
            loading="lazy"
            draggable={false}
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              // Fallback: full-page image if crop is missing.
              if (d.source_doc_slug && d.source_ref?.page) {
                img.src = documents.pageImageUrl(d.source_doc_slug, d.source_ref.page);
              } else {
                img.style.display = "none";
              }
            }}
          />
        </div>
      ) : null}

      {rows.length > 0 ? (
        <table className="w-full">
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-neutral-100 last:border-0">
                <td className="px-3 py-1 text-neutral-600">{r.key}</td>
                <td className="px-3 py-1 text-neutral-900">{r.value}</td>
                <td className="px-2 text-xs text-neutral-400">
                  {r.source_ref?.page ? `p${r.source_ref.page}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : d.description ? (
        <div className="px-3 py-2 text-[12px] text-neutral-700 leading-snug">
          {d.description}
        </div>
      ) : null}

      {d.tags && d.tags.length > 0 ? (
        <div className="flex flex-wrap gap-1 px-3 pb-2">
          {d.tags.map((t) => (
            <span
              key={t}
              className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600"
            >
              {t}
            </span>
          ))}
        </div>
      ) : null}

      <Handle type="source" position={Position.Right} />
    </div>
  );
}
