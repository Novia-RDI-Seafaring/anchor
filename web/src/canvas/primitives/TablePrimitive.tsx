import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { documents, type ResolvableRef } from "@/api/documents";
import { evidenceLabels, evidenceState, type EvidenceRow } from "@/canvas/evidence";
import { SourceAnchorButton } from "@/canvas/SourceAnchorButton";
import { resolveText } from "@/canvas/colors";
import { PlaceholderChip } from "@/canvas/PlaceholderChip";
import { placeholderState, PLACEHOLDER_BG, PLACEHOLDER_STROKE } from "@/canvas/placeholder";
import { ReviewBadge } from "@/canvas/ReviewBadge";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";
import { useUiStore } from "@/stores/uiStore";

type Row = EvidenceRow & {
  key: string;
  value: string;
  // Per-row provenance back to the source document. `region_id` is the link
  // the row-handle wiring relies on: when the user hovers a row, the spec
  // broadcasts hoveredSourceRef{slug, page, region_id, bbox}, the document
  // node flips to that page and highlights the matching region, and any
  // evidence edge whose data.source_ref matches snaps from node-to-node
  // floating to row-handle↔region-handle anchored mode.
  source_region_id?: string;
  source_ref?: {
    slug?: string;
    page: number;
    region_id?: string;
    source_region_id?: string;
    bbox?: number[];
    item_id?: string;
    cell?: { row?: number; col?: number };
  };
};

type SourceRef = {
  kind?: string;
  slug?: string;
  page?: number;
  region_id?: string;
  source_region_id?: string;
  bbox?: number[];
  // Below-region selectors (#242 P2): enriched spec rows record the matched
  // table cell; agents may name a single silver item.
  item_id?: string;
  cell?: { row?: number; col?: number };
};

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
    crops?: { png?: string | null; svg?: string | null };
    source_ref?: SourceRef;
    dashed?: boolean;
    width?: number;
    height?: number;
  };
  const canonicalRows = useMemo<Row[]>(() => d.rows ?? [], [d.rows]);
  const ph = placeholderState(d as Record<string, unknown> | undefined);
  // Placeholder mode forces dashed sky outline even if the user didn't pick
  // `data.dashed`. Filling the slot via `canvas_update_node` (placeholder:
  // false, rows: [...]) flips it back to the solid border + white bg.
  const borderStyle = ph.active || d.dashed ? "border-dashed" : "border-solid";
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
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
        region_id: d.source_ref.region_id ?? d.source_region_id ?? d.source_ref.source_region_id,
        bbox: d.source_ref.bbox,
        item_id: d.source_ref.item_id,
        cell: d.source_ref.cell,
      });
    }
  };

  /** Per-row hover broadcasts the row's own source_ref, falling back to the
   *  spec's node-level source_ref when the row hasn't been wired yet. This
   *  is what drives the document node's page-flip + region-highlight, and
   *  via pickEdgeMode the evidence edge's floating→anchored swap. */
  const broadcastRowHover = (row: Row) => {
    const ref = row.source_ref ?? d.source_ref;
    const slug = ref?.slug ?? d.source_doc_slug;
    if (!slug || !ref?.page) return;
    setHoveredSourceRef({
      slug,
      page: ref.page,
      region_id: ref.region_id ?? row.source_region_id ?? ref.source_region_id ?? d.source_region_id,
      bbox: ref.bbox,
      item_id: ref.item_id,
      cell: ref.cell,
      // Carry the cell value so the document node can draw the value-precise
      // highlight inside the region, not just the region rectangle (#197).
      query: row.value || undefined,
    });
  };

  /** Stable ReactFlow handle id for a row. Keyed on (index, key) so the id
   *  stays unique even when two rows happen to share a key string. The
   *  index keeps it stable across re-renders for the same logical row. */
  const rowHandleId = (i: number, row: Row): string =>
    `row:${i}:${(row.key || "").trim()}`;

  /** A row's or the card's stored ref, filled in from the card where the row
   *  is terse: older rows carry a page but no slug, and the region id may
   *  only exist at card level. Returns null when there is nothing to open.
   *
   *  Opening and previewing are both SourceAnchorButton's job now, so this
   *  only has to produce the ref. The button resolves the tightest box
   *  (cell > item > region > bbox) through useOpenSourceRef, and passes
   *  `documentNodeId` on so the viewer's "send region to canvas" sidebar can
   *  wire evidence edges back to the same source card. */
  const normalizeRef = (ref?: SourceRef): ResolvableRef | null => {
    const slug = ref?.slug ?? d.source_doc_slug;
    if (!slug || !ref?.page) return null;
    return {
      ...ref,
      slug,
      page: ref.page,
      region_id: ref.region_id ?? d.source_region_id ?? ref.source_region_id,
    };
  };
  const headerRef = normalizeRef(d.source_ref);

  const cropRel = d.crops?.png ?? d.crops?.svg ?? null;
  const storedCropUrl = d.source_doc_slug && cropRel ? documents.cropUrl(d.source_doc_slug, cropRel) : null;
  const renderedCropUrl = d.source_doc_slug && d.source_ref?.page && d.source_ref?.bbox
    ? documents.pageCropUrl(d.source_doc_slug, d.source_ref.page, d.source_ref.bbox)
    : null;
  const previewUrl = renderedCropUrl ?? storedCropUrl;

  const canEdit = selected ?? false;
  // Inline title rename — wires the spec table's `label` field to the same
  // hook every shape/card uses. Selection-gated (only when `selected`),
  // commits via the standard merge-with-existing-data path so the spec's
  // other data fields (rows, source_ref, …) survive. `workspaceSlug` is
  // declared earlier in this component for the broadcastHover wiring;
  // reusing it here avoids a duplicate-binding error.
  const titleEdit = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: d.label ?? "",
    field: "label",
    canEdit,
  });
  // Live-resize mirror — see useLiveResize for the rationale. When the user
  // hasn't resized yet, fall back to the Tailwind `w-72` default; once a
  // dimension is in flight or persisted, the explicit style override wins.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const sized = liveW !== undefined || liveH !== undefined;
  // A spec table is read as much as any card, so it honours the same text
  // scale the shapes do: `data.text_size` drives the rows, and the heading
  // tracks it rather than staying pinned at 10px.
  const text = resolveText(d as Record<string, unknown>);
  // Spec content is row-driven: an explicit `height` from a previous
  // resize forces empty space below the last row and visually disconnects
  // the resize box from the visible card. Use `minHeight` instead so the
  // wrapper auto-grows past the stored height when content needs more
  // room, but doesn't go smaller than the user-chosen size. Width still
  // gets honoured explicitly because the user typically resizes spec
  // tables horizontally to control column widths.
  const wrapperStyle: React.CSSProperties = sized
    ? { width: liveW, minHeight: liveH }
    : {};
  if (ph.active) {
    wrapperStyle.background = PLACEHOLDER_BG;
    wrapperStyle.borderColor = PLACEHOLDER_STROKE;
  }
  return (
    <div
      className={`relative rounded-lg border ${borderStyle} ${ph.active ? "" : "border-neutral-400 bg-white"} shadow-sm ${sized ? "" : "w-72"} ${selected ? "cursor-move" : "cursor-pointer"}`}
      style={{ ...wrapperStyle, fontSize: text.fontSize, fontFamily: text.fontFamily }}
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
      {ph.active ? <PlaceholderChip hint={ph.hint} /> : null}
      <ReviewBadge data={data as Record<string, unknown>} nodeId={id} />
      <Handle type="target" position={Position.Left} className="canvas-node-socket" />
      <div
        className="flex items-center justify-between border-b border-neutral-200 px-3 py-2 gap-2"
      >
        <div className="min-w-0">
          <div
            className="uppercase tracking-wide text-neutral-500"
            style={{ fontSize: `calc(${text.headingFontSize} * 0.85)` }}
          >
            spec
          </div>
          <div
            className="truncate font-medium text-neutral-900"
            style={{ fontSize: text.fontSize, fontFamily: text.fontFamily }}
          >
            {titleEdit.editing ? (
              <input
                {...titleEdit.inputProps}
                className={`${titleEdit.inputProps.className} w-full min-w-[6rem] truncate rounded border border-neutral-300 bg-white px-1 py-0 text-sm font-medium leading-tight outline-none focus:border-neutral-500`}
                placeholder="spec title"
              />
            ) : (
              <div
                className={canEdit ? "cursor-text" : "cursor-pointer"}
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  titleEdit.beginEdit();
                }}
                title={canEdit ? "double-click to rename" : undefined}
              >
                {d.label || <span className="text-neutral-400">untitled spec</span>}
              </div>
            )}
          </div>
        </div>
        {/* The header anchor is the fallback for rows without their own
            reference. When every row is grounded, each row's anchor already
            opens its source, so a card-level anchor would be redundant. */}
        {headerRef && !(rows.length > 0 && rows.every((r) => r.source_ref?.page)) ? (
          <SourceAnchorButton
            workspaceSlug={workspaceSlug}
            documentNodeId={d.source_doc_node_id}
            refValue={headerRef}
            title={`Open page ${headerRef.page} in viewer`}
            ariaLabel={`Open source page ${headerRef.page}`}
            size={12}
            className="h-6 w-6 shrink-0 border border-sky-300 bg-sky-50"
          />
        ) : null}
      </div>

      {previewUrl ? (
        <div className="border-b border-neutral-200 bg-neutral-50">
          <img
            src={previewUrl}
            alt={d.label ?? "region"}
            className="block max-h-32 w-full object-contain"
            loading="lazy"
            draggable={false}
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              if (storedCropUrl && img.dataset.cropFallback !== "stored") {
                img.dataset.cropFallback = "stored";
                img.src = storedCropUrl;
                return;
              }
              if (d.source_doc_slug && d.source_ref?.page) {
                img.src = documents.pageImageUrl(d.source_doc_slug, d.source_ref.page);
              } else {
                img.style.display = "none";
              }
            }}
          />
        </div>
      ) : null}

      {/* Fixed layout: with `auto`, a long key or value sets the table's
          min-content width and the rows spill past the card's right edge
          (the wrapper has a fixed width). Fixed layout keeps the table at
          the card width and lets the cells' `truncate` do the clipping;
          the last column reserves room for evidence status and source actions. */}
      {rows.length > 0 || !d.description ? (
        <table className="w-full table-fixed">
          <colgroup>
            <col style={{ width: "45%" }} />
            <col />
            <col style={{ width: "5rem" }} />
          </colgroup>
          <tbody>
            {rows.map((r, i) => {
              const hid = rowHandleId(i, r);
              const status = evidenceState(r);
              const evidenceLabel = evidenceLabels[status];
              const rowRef = normalizeRef(r.source_ref);
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
                  <td className="min-w-0 px-3 py-1 text-neutral-600">
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
                  <td className={`min-w-0 px-3 py-1 text-neutral-900 ${status === "verified" ? "bg-emerald-50/80" : ""}`}>
                    <RowCell
                      rowIndex={i}
                      col="value"
                      value={r.value}
                      rowsLen={rows.length}
                      canEdit={canEdit}
                      // Grounded values get a yellow "marker pen" highlight on
                      // row hover, so the eye lands on the exact value while the
                      // source node highlights where it came from (issue #145).
                      marker={status === "verified"}
                      pendingFocus={pendingFocus}
                      setPendingFocus={setPendingFocus}
                      onCommit={(v) => commitRow(i, "value", v)}
                      onAppendRow={() => appendRow("key")}
                    />
                  </td>
                  <td className="relative w-20 px-2 text-xs text-neutral-400">
                    {/* Only a status worth acting on earns a word. "Unverified"
                        and "No evidence" were printed on every ungrounded row,
                        which is most of them while a spec is being built: a
                        column of grey labels that say nothing happened. The
                        state is still readable -- verified rows are tinted and
                        carry a tick, everything else is plain -- and the full
                        wording stays in the tooltip. */}
                    <span
                      aria-label={`Evidence: ${evidenceLabel}`}
                      title={status === "verified" ? "Validated for this claim at the recorded source generation" :
                        status === "stale" ? "Claim or evidence changed. Revalidate before relying on this citation." :
                          status === "unverified" ? "Source link exists; this claim has not been verified." : "No source evidence"}
                      data-evidence-status={status}
                      className={`block text-[10px] ${status === "verified" ? "text-emerald-700" : "text-amber-800"}`}
                    >{status === "verified" ? "✓" : status === "stale" ? evidenceLabel : ""}</span>
                    {rowRef ? (
                      <SourceAnchorButton
                        workspaceSlug={workspaceSlug}
                        documentNodeId={d.source_doc_node_id}
                        refValue={rowRef}
                        query={status === "verified" ? r.value || undefined : undefined}
                        title={`Open page ${rowRef.page} in viewer`}
                        ariaLabel={`Open source page ${rowRef.page}`}
                        className="h-5 w-5"
                      />
                    ) : null}
                    {/* Revalidation is an action, not a status, so it shows up
                        when the pointer is on the row rather than sitting in
                        the card permanently. */}
                    {canEdit && r.source_ref && status !== "verified" ? (
                      <button type="button"
                        title="Re-check this claim against its source"
                        className="nodrag nopan text-[10px] underline text-neutral-700 opacity-0 transition group-hover/tr:opacity-100 focus:opacity-100"
                        aria-label={`Revalidate evidence for ${r.key}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          persistRows(rows.map((row, j) => j === i ? { ...row, revalidate_evidence: true } : row));
                        }}
                      >Check</button>
                    ) : null}
                    {/* Per-row source handle. Never visible or grabbable
                        (see the handle rule in index.css): it only gives an
                        anchored evidence edge a slot to pin to while its row
                        is hovered. */}
                    <Handle
                      type="source"
                      position={Position.Right}
                      id={hid}
                      className="canvas-row-socket !h-2 !w-2 !min-w-0 !min-h-0 !border !border-neutral-400 !bg-white opacity-30 transition group-hover/tr:opacity-100 hover:!opacity-100 hover:!border-emerald-600 hover:!bg-emerald-400"
                      style={{ right: -4 }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <div className="px-3 py-2 text-neutral-700 leading-snug">
          {d.description}
        </div>
      )}

      {canEdit ? (
        <div className="flex items-center justify-end border-t border-neutral-100 px-2 py-1">
          <button
            type="button"
            className="nodrag nopan rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800"
            onMouseDown={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
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

      <Handle type="source" position={Position.Right} className="canvas-node-socket" />
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
  marker = false,
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
  /** When true, the displayed value is highlighted with a yellow marker on
   *  row hover (the grounded-value affordance, issue #145). */
  marker?: boolean;
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
  // A grounded value uses an inline-block marker span so the yellow highlight
  // hugs the text (marker-pen look) rather than filling the whole cell, while
  // still truncating long values. Plain cells stay a simple block span.
  const markerClass = marker
    ? "nodrag inline-block max-w-full truncate align-bottom rounded-sm px-0.5 -mx-0.5 transition-colors duration-100 group-hover/tr:bg-yellow-200 group-hover/tr:text-neutral-900"
    : "nodrag block truncate";
  return (
    <span
      data-testid={marker ? "spec-value-marker" : undefined}
      className={`${markerClass} ${canEdit ? "cursor-text" : "cursor-pointer"}`}
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
