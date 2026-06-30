import { useCallback, useEffect, useRef, useState } from "react";

import { documents } from "@/api/documents";
import {
  REFERENCES_CHANGED_EVENT,
  references,
} from "@/api/references";
import type { Reference } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

/**
 * ReferencesPanel — the canvas bibliography, docked on the LEFT above the PDF
 * source pane (#147 slice 3). It lists the current canvas's references, opens a
 * reference's source in the shared PDF dock at its page + bbox, and lets the
 * user rename or delete an entry.
 *
 * Live-update: the panel refetches on the `anchor:references-changed` browser
 * event the references API emits after any mutate (create from the PDF dock's
 * "Make reference" flow, or this panel's own rename/delete). The workspace SSE
 * carries the canvas graph, not the metadata bibliography, so this UI-only
 * nudge is what makes a freshly-made reference appear without a reload.
 *
 * Visual language matches the shell panels (CanvasesPanel / Library): small
 * uppercase section header, bordered rows, neutral palette, dense type.
 */
type Props = { canvasSlug: string };

export function ReferencesPanel({ canvasSlug }: Props) {
  const [items, setItems] = useState<Reference[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const openPdf = useUiStore((s) => s.openPdf);

  const refresh = useCallback(async () => {
    try {
      const list = await references.list(canvasSlug);
      setItems(list);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [canvasSlug]);

  // Initial load + refetch when references change in this window.
  useEffect(() => {
    setLoading(true);
    void refresh();
    const onChanged = (ev: Event) => {
      const detail = (ev as CustomEvent<{ slug?: string }>).detail;
      // Ignore mutations on other canvases sharing the same window.
      if (detail?.slug && detail.slug !== canvasSlug) return;
      void refresh();
    };
    window.addEventListener(REFERENCES_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(REFERENCES_CHANGED_EVENT, onChanged);
  }, [canvasSlug, refresh]);

  const openSource = useCallback(
    (ref: Reference) => {
      const sr = ref.source_ref;
      openPdf(sr.slug, {
        page: sr.page,
        mode: "dock",
        workspaceSlug: canvasSlug,
        highlightRegionId: sr.region_id,
        highlightBbox: sr.bbox,
        highlightQuery: sr.detail?.quote,
      });
    },
    [openPdf, canvasSlug],
  );

  const onDelete = useCallback(
    async (ref: Reference) => {
      // Optimistic drop; refetch reconciles on the changed-event anyway.
      setItems((prev) => prev.filter((r) => r.id !== ref.id));
      try {
        await references.remove(canvasSlug, ref.id);
      } catch (e) {
        setError(String(e));
        void refresh();
      }
    },
    [canvasSlug, refresh],
  );

  const onRename = useCallback(
    async (ref: Reference, label: string) => {
      const next = label.trim() || null;
      setItems((prev) =>
        prev.map((r) => (r.id === ref.id ? { ...r, label: next ?? undefined } : r)),
      );
      try {
        await references.update(canvasSlug, ref.id, { label: next });
      } catch (e) {
        setError(String(e));
        void refresh();
      }
    },
    [canvasSlug, refresh],
  );

  return (
    <div
      className="flex max-h-[45%] min-h-0 shrink-0 flex-col border-b border-neutral-200 bg-white"
      data-testid="references-panel"
    >
      <div className="flex items-baseline justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          References ({items.length})
        </span>
        <span className="text-[9px] italic text-neutral-400">
          click to open source
        </span>
      </div>
      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-1.5">
        {loading ? (
          <Hint text="loading references…" />
        ) : error ? (
          <div className="px-2 text-[10px] text-red-600">error: {error}</div>
        ) : items.length === 0 ? (
          <Hint text="no references yet — select source content and choose 'Make reference'" />
        ) : (
          items.map((ref) => (
            <ReferenceRow
              key={ref.id}
              reference={ref}
              onOpen={() => openSource(ref)}
              onDelete={() => onDelete(ref)}
              onRename={(label) => onRename(ref, label)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function Hint({ text }: { text: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
      {text}
    </div>
  );
}

/**
 * The row's primary line: the human caption, else a short quote snippet, else
 * a generic placeholder. The slug + page always render on a separate subtitle
 * line, so the title never duplicates them.
 */
function referenceTitle(ref: Reference): string {
  if (ref.label && ref.label.trim()) return ref.label.trim();
  const quote = ref.source_ref.detail?.quote?.trim();
  if (quote) return quote.length > 60 ? `${quote.slice(0, 57)}…` : quote;
  return "Untitled reference";
}

function ReferenceRow({
  reference,
  onOpen,
  onDelete,
  onRename,
}: {
  reference: Reference;
  onOpen: () => void;
  onDelete: () => void;
  onRename: (label: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(reference.label ?? "");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const sr = reference.source_ref;
  const quote = sr.detail?.quote?.trim();
  // A crop thumbnail is only meaningful when we have a geometric bbox.
  const thumbUrl =
    sr.bbox && sr.bbox.length === 4
      ? documents.pageCropUrl(sr.slug, sr.page, sr.bbox, 96)
      : null;

  const commit = () => {
    setEditing(false);
    if (draft !== (reference.label ?? "")) onRename(draft);
  };

  return (
    <div
      className="group rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs hover:bg-neutral-50"
      data-testid="reference-row"
    >
      <div className="flex items-start gap-2">
        {thumbUrl ? (
          <button
            type="button"
            onClick={onOpen}
            className="shrink-0 overflow-hidden rounded border border-neutral-200 bg-neutral-50"
            title="Open source"
            aria-label="Open source"
          >
            <img
              src={thumbUrl}
              alt=""
              className="h-9 w-12 object-cover"
              loading="lazy"
            />
          </button>
        ) : null}
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit();
                if (e.key === "Escape") {
                  setDraft(reference.label ?? "");
                  setEditing(false);
                }
              }}
              className="w-full rounded border border-neutral-300 px-1 py-0.5 text-xs"
              placeholder="reference label"
              aria-label="Reference label"
              data-testid="reference-label-input"
            />
          ) : (
            <button
              type="button"
              onClick={onOpen}
              className="block w-full truncate text-left font-medium text-neutral-800"
              title="Open source"
              data-testid="reference-open"
            >
              {referenceTitle(reference)}
            </button>
          )}
          <div className="mt-0.5 truncate text-[10px] text-neutral-500">
            {sr.slug} · p.{sr.page}
          </div>
          {quote && !editing ? (
            <div className="mt-0.5 line-clamp-2 text-[10px] italic text-neutral-400">
              “{quote}”
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={() => {
              setDraft(reference.label ?? "");
              setEditing(true);
            }}
            className="rounded px-1 text-[10px] text-neutral-500 hover:bg-neutral-200"
            title="Rename label"
            aria-label="Rename reference"
            data-testid="reference-rename"
          >
            ✎
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded px-1 text-[10px] text-neutral-500 hover:bg-red-100 hover:text-red-600"
            title="Delete reference"
            aria-label="Delete reference"
            data-testid="reference-delete"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
