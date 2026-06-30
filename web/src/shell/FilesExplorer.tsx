/**
 * FilesExplorer — the left-edge file list of the source cluster (#220 part B).
 *
 * VS Code / Cursor model: ingested artefacts live here at the far left, the
 * PDF viewer sits immediately to the right, the canvas after that, and the
 * inspector (Properties) on the far right. This component replaces the retired
 * right-side Library drawer; its Documents + CAD lists moved here, and the
 * Canvases list keeps a home as a second tab.
 *
 * Two interactions per document row:
 *   1. Click  -> open it in the shared PDF viewer (dock mode), to the right.
 *      The open document is highlighted as active.
 *   2. Drag   -> drop on the canvas to instantiate a node. The drag payloads
 *      are byte-for-byte the ones the old Library used so CanvasGraph's drop
 *      handler is untouched: `application/x-anchor-node` for documents + CAD,
 *      `application/x-anchor-canvas-link` for canvases.
 */
import { useEffect, useRef, useState } from "react";

import { cad, type CadModel } from "@/api/cad";
import {
  canvases,
  type WorkspaceListEntry,
} from "@/api/canvases";
import { documents, type DocumentSummary } from "@/api/documents";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/uiStore";

import {
  CANVAS_LINK_MIME,
  filterAttachable,
  type CanvasLinkPayload,
} from "./CanvasesPanel";

type Props = { workspaceSlug: string };

type TabKey = "files" | "canvases";

export function FilesExplorer({ workspaceSlug }: Props) {
  const [tab, setTab] = useState<TabKey>("files");
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [cads, setCads] = useState<CadModel[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceListEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const openPdf = useUiStore((s) => s.openPdf);
  // The active document is whatever the shared viewer currently shows.
  const activeSlug = useUiStore((s) => s.pdfViewer?.slug ?? null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [d, c, w] = await Promise.all([
          documents.list().catch(() => [] as DocumentSummary[]),
          cad.list().catch(() => [] as CadModel[]),
          canvases.list().catch(() => [] as WorkspaceListEntry[]),
        ]);
        if (!cancelled) {
          setDocs(d);
          setCads(c);
          setWorkspaces(w);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    };

    refresh();
    // Light polling — every 8s, matching the old Library cadence. SSE for the
    // documents/cad/workspaces lists isn't wired yet.
    const id = window.setInterval(refresh, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const openDocument = (slug: string) => {
    // Dock mode, wired to this canvas so "send to canvas" + the references
    // panel work. Reuses the exact action the canvas primitives call.
    openPdf(slug, { mode: "dock", workspaceSlug });
  };

  const visibleCanvases = filterAttachable(workspaces, workspaceSlug);

  return (
    <div className="flex h-full min-h-0 flex-col bg-white" data-testid="files-explorer">
      {/* Tabs: Files (documents + CAD) and Canvases. */}
      <div
        className="flex shrink-0 items-center gap-1 border-b border-neutral-200 bg-neutral-50 px-1.5 py-1"
        role="tablist"
        aria-label="Explorer sections"
      >
        <ExplorerTab
          label="Files"
          active={tab === "files"}
          onClick={() => setTab("files")}
        />
        <ExplorerTab
          label="Canvases"
          active={tab === "canvases"}
          onClick={() => setTab("canvases")}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {tab === "files" ? (
          <div className="space-y-3">
            <Section title={`Documents (${docs.length})`} subtitle="anchor_pdfs">
              {docs.length === 0 ? (
                <Empty hint="ingest a PDF — drop it on the canvas or use anchor ingest" />
              ) : (
                docs.map((d) => (
                  <DocumentItem
                    key={d.slug}
                    doc={d}
                    active={d.slug === activeSlug}
                    onOpen={() => openDocument(d.slug)}
                  />
                ))
              )}
            </Section>

            <Section title={`CAD models (${cads.length})`} subtitle="anchor_cad">
              {cads.length === 0 ? (
                <Empty hint="no CAD models yet — use cad.inspect via MCP" />
              ) : (
                cads.map((c) => (
                  <DraggableItem
                    key={c.slug}
                    label={c.title || c.filename || c.slug}
                    hint={`${c.kind}${c.geometry?.triangle_count ? ` · ${c.geometry.triangle_count} tris` : ""}`}
                    payload={{
                      node_type: "cad:model",
                      label: c.title || c.filename || c.slug,
                      data: {
                        cad_slug: c.slug,
                        kind: c.kind,
                        parameters: c.parameters?.map((p) => p.name) ?? [],
                      },
                    }}
                  />
                ))
              )}
            </Section>
          </div>
        ) : (
          <div className="space-y-3">
            <Section title={`Canvases (${visibleCanvases.length})`} subtitle="drag to link">
              {visibleCanvases.length === 0 ? (
                <Empty hint="no other canvases to link — create one from the canvases list" />
              ) : (
                visibleCanvases.map((c) => (
                  <DraggableCanvasItem key={c.slug} entry={c} />
                ))
              )}
            </Section>
          </div>
        )}

        {error ? (
          <div className="px-2 pt-2 text-[10px] text-red-600">error: {error}</div>
        ) : null}
      </div>
    </div>
  );
}

function ExplorerTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded px-2 py-1 text-[11px] font-medium transition",
        active
          ? "bg-white text-neutral-900 shadow-sm ring-1 ring-neutral-200"
          : "text-neutral-500 hover:bg-neutral-100",
      )}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// DocumentItem — clickable + draggable row for a single document. Clicking
// opens it in the viewer; the active document is highlighted. Drag emits the
// same `application/x-anchor-node` payload the old Library used.
// ---------------------------------------------------------------------------

function DocumentItem({
  doc,
  active,
  onOpen,
}: {
  doc: DocumentSummary;
  active: boolean;
  onOpen: () => void;
}) {
  const [imgError, setImgError] = useState(false);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewImgError, setPreviewImgError] = useState(false);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const thumbnailUrl = documents.pageImageUrl(doc.slug, 1);
  const hint = `${doc.page_count}p${doc.has_gold ? " · gold" : ""}`;
  const payload = {
    node_type: "document",
    label: doc.title || doc.filename,
    data: {
      slug: doc.slug,
      filename: doc.filename,
      page_count: doc.page_count,
      region_count: doc.region_count,
      status: "ready",
    },
  };

  const showPreview = () => {
    hoverTimerRef.current = setTimeout(() => setPreviewVisible(true), 300);
  };
  const hidePreview = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    setPreviewVisible(false);
  };

  return (
    <div className="relative">
      <div
        draggable
        role="button"
        tabIndex={0}
        data-testid="document-item"
        data-slug={doc.slug}
        data-active={active ? "true" : "false"}
        aria-current={active ? "true" : undefined}
        onClick={onOpen}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpen();
          }
        }}
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = "copy";
          e.dataTransfer.setData("application/x-anchor-node", JSON.stringify(payload));
        }}
        onMouseEnter={showPreview}
        onMouseLeave={hidePreview}
        onFocus={showPreview}
        onBlur={hidePreview}
        onContextMenu={(e) => {
          // Right-click shows preview immediately.
          e.preventDefault();
          setPreviewVisible((v) => !v);
        }}
        className={cn(
          "cursor-grab rounded border bg-white hover:bg-neutral-50 active:cursor-grabbing",
          active
            ? "border-sky-300 bg-sky-50 ring-1 ring-sky-300"
            : "border-neutral-200",
        )}
        title={doc.slug}
      >
        <div className="flex items-center gap-2 px-2 py-1.5">
          {/* Thumbnail */}
          <div className="shrink-0">
            {imgError ? (
              <div
                data-testid="thumbnail-fallback"
                className="flex h-10 w-8 items-center justify-center rounded bg-neutral-100 text-[14px] text-neutral-400"
              >
                ▤
              </div>
            ) : (
              <img
                data-testid="thumbnail-img"
                src={thumbnailUrl}
                alt={doc.filename}
                loading="lazy"
                className="h-10 w-8 rounded object-cover object-top"
                onError={() => setImgError(true)}
              />
            )}
          </div>

          {/* Text */}
          <div className="min-w-0 flex-1">
            <div
              className={cn(
                "truncate text-xs font-medium",
                active ? "text-sky-900" : "text-neutral-800",
              )}
            >
              {doc.title || doc.slug}
            </div>
            <div className="truncate text-[10px] text-neutral-500" data-testid="doc-filename">
              {doc.filename}
            </div>
            <div className="text-[9px] italic text-neutral-400">{hint}</div>
          </div>
        </div>
      </div>

      {/* Hover preview popover */}
      {previewVisible ? (
        <div
          data-testid="hover-preview"
          className="absolute left-full top-0 z-50 ml-2 w-56 rounded border border-neutral-200 bg-white shadow-lg"
          onMouseEnter={() => {
            if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
          }}
          onMouseLeave={hidePreview}
        >
          <div className="p-1.5">
            {previewImgError ? (
              <div className="flex h-36 w-full items-center justify-center rounded bg-neutral-100 text-sm text-neutral-400">
                no preview
              </div>
            ) : (
              <img
                src={thumbnailUrl}
                alt={doc.filename}
                className="w-full rounded"
                onError={() => setPreviewImgError(true)}
              />
            )}
          </div>
          <div className="border-t border-neutral-100 px-2 py-1.5">
            <div className="truncate text-xs font-medium text-neutral-800">
              {doc.title || doc.slug}
            </div>
            <div className="truncate text-[10px] text-neutral-500">{doc.filename}</div>
            <div className="mt-0.5 font-mono text-[9px] text-neutral-400">{doc.slug}</div>
            <div className="mt-0.5 text-[9px] text-neutral-400">
              {doc.page_count} {doc.page_count === 1 ? "page" : "pages"}
              {doc.has_gold ? " · gold" : ""}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between px-1 pt-1 pb-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          {title}
        </div>
        {subtitle ? (
          <div className="text-[9px] italic text-neutral-400">{subtitle}</div>
        ) : null}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Empty({ hint }: { hint: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
      {hint}
    </div>
  );
}

function DraggableItem({
  label,
  hint,
  payload,
}: {
  label: string;
  hint: string;
  payload: { node_type: string; label?: string; data?: Record<string, unknown> };
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData("application/x-anchor-node", JSON.stringify(payload));
      }}
      className="cursor-grab rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs hover:bg-neutral-50 active:cursor-grabbing"
      title={hint}
    >
      <div className="truncate font-medium text-neutral-800">{label}</div>
      <div className="text-[10px] italic text-neutral-500">{hint}</div>
    </div>
  );
}

function DraggableCanvasItem({ entry }: { entry: WorkspaceListEntry }) {
  const title = entry.title || entry.slug;
  const hasCounts =
    typeof entry.node_count === "number" && typeof entry.edge_count === "number";
  const stats = hasCounts
    ? `${entry.node_count} nodes · ${entry.edge_count} edges`
    : entry.slug;

  return (
    <div
      draggable
      data-testid="canvas-link-item"
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "link";
        const payload: CanvasLinkPayload = { slug: entry.slug, title };
        e.dataTransfer.setData(CANVAS_LINK_MIME, JSON.stringify(payload));
      }}
      className="cursor-grab rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs hover:bg-neutral-50 active:cursor-grabbing"
      title={`Link existing canvas (${entry.slug})`}
    >
      <div className="flex items-center gap-1.5 truncate font-medium text-neutral-800">
        <CanvasGlyph />
        <span className="truncate">{title}</span>
        {entry.title ? (
          <span className="truncate text-[10px] font-normal text-neutral-400">
            ({entry.slug})
          </span>
        ) : null}
      </div>
      <div className="text-[10px] italic text-neutral-500">{stats}</div>
    </div>
  );
}

function CanvasGlyph() {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      className="shrink-0 text-neutral-500"
      aria-hidden="true"
    >
      <polygon points="6,1 11,3.5 11,8.5 6,11 1,8.5 1,3.5" />
    </svg>
  );
}
