import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { documents } from "@/api/documents";
import { useLiveResize } from "@/canvas/useLiveResize";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

type Row = {
  key: string;
  value: string;
  // Per-row provenance back to the source document. `region_id` is the link
  // the row-handle wiring relies on: when the user hovers a row, the spec
  // broadcasts hoveredSourceRef{slug, page, region_id, bbox}, the document
  // node flips to that page and highlights the matching region, and any
  // evidence edge whose data.source_ref matches snaps from node-to-node
  // floating to row-handle↔region-handle anchored mode.
  source_ref?: { page: number; region_id?: string; bbox?: number[] };
};

type SourceRef = { kind?: string; page?: number; bbox?: number[] };

/**
 * TablePrimitive — `spec` node renderer.
 *
 * Rows are minimally editable inline (per-cell `key` / `value`). Source refs
 * (page + bbox) are not editable here; those are owned by the Properties
 * panel and the future row-handle wiring (task #46).
 *
 * Keyboard map per cell:
 *   - Plain Enter  → commit cell, jump focus to the next cell (key → value
 *                    → next row's key). At the very last cell, plain Enter
 *                    commits and blurs (no row append).
 *   - Shift+Enter  → at the last row's value cell, append a new empty row
 *                    and focus its `key`. Elsewhere it commits like Enter.
 *   - Esc          → cancel the pending edit and exit.
 *   - Click "+ row" → explicit append.
 *
 * Persistence: every commit issues a `canvases.patchNode(slug, id, { data:
 * { rows: [...] } })`. The store-driven `data.rows` re-renders via SSE so
 * the local state stays in sync with the canonical canvas.
 */
export function TablePrimitive({ id, data, selected }: NodeProps) {
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
    width?: number;
    height?: number;
  };
  const canonicalRows = useMemo<Row[]>(() => d.rows ?? [], [d.rows]);
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  const openPdf = useUiStore((s) => s.openPdf);
  const { id: workspaceSlug } = useParams<{ id: string }>();

  // Local working copy of rows so cell edits feel snappy. Replaced when
  // the canonical rows change from outside (SSE echo, remote agent edit).
  const [rows, setRows] = useState<Row[]>(canonicalRows);
  // Track which row index is "pending focus" so the cell can grab focus
  // after the new row mounts. -1 means no pending focus.
  const [pendingFocus, setPendingFocus] = useState<{ row: number; col: "key" | "value" } | null>(
    null,
  );
  useEffect(() => {
    setRows(canonicalRows);
  }, [canonicalRows]);

  const persistRows = (next: Row[]) => {
    if (!workspaceSlug) return;
    canvases
      .patchNode(workspaceSlug, id, { data: { ...(d ?? {}), rows: next } })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("row edit failed", err);
      });
  };

  const commitRow = (index: number, col: "key" | "value", next: string) => {
    setRows((prev) => {
      const trimmed = next.replace(/\s+$/g, "");
      const existing = prev[index];
      if (!existing) return prev;
      if (existing[col] === trimmed) return prev;
      const draft = [...prev];
      draft[index] = { ...existing, [col]: trimmed };
      persistRows(draft);
      return draft;
    });
  };

  const appendRow = (focusCol: "key" | "value" = "key") => {
    setRows((prev) => {
      const draft = [...prev, { key: "", value: "" }];
      persistRows(draft);
      setPendingFocus({ row: draft.length - 1, col: focusCol });
      return draft;
    });
  };

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

  /** Per-row hover broadcasts the row's own source_ref, falling back to the
   *  spec's node-level source_ref when the row hasn't been wired yet. This
   *  is what drives the document node's page-flip + region-highlight, and
   *  via pickEdgeMode the evidence edge's floating→anchored swap. */
  const broadcastRowHover = (row: Row) => {
    if (!d.source_doc_slug) return;
    const ref = row.source_ref ?? d.source_ref;
    if (!ref?.page) return;
    setHoveredSourceRef({
      slug: d.source_doc_slug,
      page: ref.page,
      region_id: row.source_ref?.region_id ?? d.source_region_id,
      bbox: ref.bbox,
    });
  };

  /** Stable ReactFlow handle id for a row. Keyed on (index, key) so the id
   *  stays unique even when two rows happen to share a key string. The
   *  index keeps it stable across re-renders for the same logical row. */
  const rowHandleId = (i: number, row: Row): string =>
    `row:${i}:${(row.key || "").trim()}`;

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

  const canEdit = selected ?? false;
  // Live-resize mirror — see useLiveResize for the rationale. When the user
  // hasn't resized yet, fall back to the Tailwind `w-72` default; once a
  // dimension is in flight or persisted, the explicit style override wins.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const sized = liveW !== undefined || liveH !== undefined;
  return (
    <div
      className={`relative rounded-lg border ${borderStyle} border-neutral-400 bg-white text-sm shadow-sm ${sized ? "" : "w-72"} ${selected ? "cursor-move" : "cursor-pointer"}`}
      style={sized ? { width: liveW, height: liveH } : undefined}
      onMouseEnter={broadcastHover}
      onMouseLeave={clearHoveredSourceRef}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={200}
        minHeight={64}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      <div
        className={`flex items-center justify-between border-b border-neutral-200 px-3 py-2 gap-2 ${
          canOpen ? "cursor-pointer hover:bg-sky-50/60" : ""
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
            canOpen ? "cursor-pointer" : ""
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

      {rows.length > 0 || !d.description ? (
        <table className="w-full">
          <tbody>
            {rows.map((r, i) => {
              const hid = rowHandleId(i, r);
              return (
                <tr
                  key={`row-${i}`}
                  data-row-handle-id={hid}
                  className="group/tr relative border-b border-neutral-100 last:border-0 hover:bg-sky-50/40"
                  // Only broadcast on row-enter; the parent <div>'s
                  // mouseLeave clears the global hover state when the
                  // cursor leaves the whole card. Clearing on row-leave
                  // would flicker when sliding between adjacent rows.
                  onMouseEnter={() => broadcastRowHover(r)}
                >
                  <td className="px-3 py-1 text-neutral-600">
                    <RowCell
                      rowIndex={i}
                      col="key"
                      value={r.key}
                      rowsLen={rows.length}
                      canEdit={canEdit}
                      pendingFocus={pendingFocus}
                      setPendingFocus={setPendingFocus}
                      onCommit={(v) => commitRow(i, "key", v)}
                      onAppendRow={() => appendRow("key")}
                    />
                  </td>
                  <td className="px-3 py-1 text-neutral-900">
                    <RowCell
                      rowIndex={i}
                      col="value"
                      value={r.value}
                      rowsLen={rows.length}
                      canEdit={canEdit}
                      pendingFocus={pendingFocus}
                      setPendingFocus={setPendingFocus}
                      onCommit={(v) => commitRow(i, "value", v)}
                      onAppendRow={() => appendRow("key")}
                    />
                  </td>
                  <td className="relative px-2 text-xs text-neutral-400">
                    {r.source_ref?.page ? `p${r.source_ref.page}` : ""}
                    {/* Per-row source handle. Default state is a 2px grey
                        dot tucked against the row's right edge — visible
                        on hover, hit-target stays clickable for drag-to-
                        connect via ReactFlow's onConnect.
                        We pin the handle inside the row's last <td> so the
                        top offset comes from layout flow (no absolute Y
                        math) and the X is right at the table's right edge. */}
                    <Handle
                      type="source"
                      position={Position.Right}
                      id={hid}
                      className="!h-2 !w-2 !min-w-0 !min-h-0 !border !border-neutral-400 !bg-white opacity-30 transition group-hover/tr:opacity-100 hover:!opacity-100 hover:!border-sky-500 hover:!bg-sky-400"
                      style={{ right: -4 }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <div className="px-3 py-2 text-[12px] text-neutral-700 leading-snug">
          {d.description}
        </div>
      )}

      {canEdit ? (
        <div className="flex items-center justify-end border-t border-neutral-100 px-2 py-1">
          <button
            type="button"
            className="nodrag nopan rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              appendRow("key");
            }}
            title="add row"
          >
            + row
          </button>
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

/**
 * One inline-editable table cell. Double-click (or focus) to edit; Enter
 * commits and tabs to the next cell; Shift+Enter at the last row's value
 * appends a new row and focuses its key.
 */
function RowCell({
  rowIndex,
  col,
  value,
  rowsLen,
  canEdit,
  pendingFocus,
  setPendingFocus,
  onCommit,
  onAppendRow,
}: {
  rowIndex: number;
  col: "key" | "value";
  value: string;
  rowsLen: number;
  canEdit: boolean;
  pendingFocus: { row: number; col: "key" | "value" } | null;
  setPendingFocus: (next: { row: number; col: "key" | "value" } | null) => void;
  onCommit: (next: string) => void;
  onAppendRow: () => void;
}) {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Reset the draft when the canonical value changes from outside.
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  // External focus requests (e.g. "Shift+Enter appended a new row; focus
  // the new row's key cell"). The parent sets `pendingFocus`; we pick it up
  // here and trigger edit mode. Only the selected node's cells respond.
  useEffect(() => {
    if (!pendingFocus) return;
    if (pendingFocus.row !== rowIndex || pendingFocus.col !== col) return;
    if (!canEdit) return;
    setDraft(value);
    setEditing(true);
    // Clear the pending focus so it doesn't re-fire after blur.
    setPendingFocus(null);
  }, [pendingFocus, rowIndex, col, value, setPendingFocus, canEdit]);

  // Commit any in-flight edit when the node becomes deselected. Draw.io
  // rule: click-outside both deselects and commits.
  useEffect(() => {
    if (canEdit) return;
    if (!editing) return;
    setEditing(false);
    if (draft !== value) onCommit(draft);
  }, [canEdit, editing, draft, value, onCommit]);

  // Focus the input when we enter edit mode.
  useEffect(() => {
    if (!editing) return;
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };
  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };

  const isLastRow = rowIndex === rowsLen - 1;

  const handleKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      // Persist before requesting focus so the parent's `rows` is in sync.
      if (draft !== value) onCommit(draft);
      setEditing(false);
      if (event.shiftKey && isLastRow && col === "value") {
        // Shift+Enter at last row's value → append a new row.
        onAppendRow();
        return;
      }
      // Plain Enter → tab to next cell: key → value → next row's key.
      if (col === "key") {
        setPendingFocus({ row: rowIndex, col: "value" });
      } else if (col === "value" && !isLastRow) {
        setPendingFocus({ row: rowIndex + 1, col: "key" });
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      cancel();
      return;
    }
    // Stop ReactFlow from hijacking keystrokes (Backspace delete-node etc.).
    event.stopPropagation();
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKey}
        onBlur={commit}
        onMouseDown={(e) => e.stopPropagation()}
        className="nodrag w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[12px] outline-none focus:border-neutral-500"
        placeholder={col === "key" ? "name" : "value"}
      />
    );
  }
  return (
    <span
      className={`nodrag block truncate ${canEdit ? "cursor-text" : "cursor-pointer"}`}
      onDoubleClick={(e) => {
        if (!canEdit) return;
        e.stopPropagation();
        setDraft(value);
        setEditing(true);
      }}
      onClick={(e) => {
        // Selection-gated: a click only enters edit mode after the node is
        // selected. The first click selects (handled by ReactFlow → the
        // outer node), and the second click on the same cell edits.
        if (!canEdit) return;
        e.stopPropagation();
        setDraft(value);
        setEditing(true);
      }}
      title={canEdit ? "click to edit" : undefined}
    >
      {value || <span className="italic text-neutral-300">{col === "key" ? "name" : "value"}</span>}
    </span>
  );
}
