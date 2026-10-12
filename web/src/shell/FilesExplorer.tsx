/**
 * FilesExplorer: canvas sources and project files in the source cluster.
 *
 * Sources derives a document dock from the current canvas's citations. Files
 * keeps the project-wide document and CAD library. Both use the shared PDF
 * viewer; a source citation does not need a document card or an evidence hub.
 *
 * Two interactions per document row:
 *   1. Click  -> open it in the shared PDF viewer (dock mode).
 *      The open document is highlighted as active.
 *   2. Drag   -> drop on the canvas to instantiate a node. The drag payloads
 *      are byte-for-byte the ones the old Library used so CanvasGraph's drop
 *      handler is untouched: `application/x-anchor-node` for documents + CAD,
 *      `application/x-anchor-canvas-link` for canvases.
 */
import { FileText } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { cad, type CadModel } from "@/api/cad";
import {
  canvases,
  type WorkspaceListEntry,
} from "@/api/canvases";
import { ReferencesPanel } from "@/canvas/primitives/viewers/ReferencesPanel";
import { useOpenSourceRef } from "@/canvas/useOpenSourceRef";
import { documents, type DocumentSummary } from "@/api/documents";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import {
  CANVAS_LINK_MIME,
  filterAttachable,
  type CanvasLinkPayload,
} from "./CanvasesPanel";
import { IntentsPanel } from "./IntentsPanel";
import { useIntentsFeed } from "./intentsFeed";
import { ProposalsPanel } from "./ProposalsPanel";
import { useProposalSetsFeed } from "./proposalSetsFeed";
import { canvasSources, type CanvasSource } from "./canvasSources";

type Props = { workspaceSlug: string };

type TabKey = "sources" | "files" | "canvases" | "references" | "intents" | "proposals";

export function FilesExplorer({ workspaceSlug }: Props) {
  const [tab, setTab] = useState<TabKey>("sources");
  // Mounted here (not in the panel) so the Intents tab badge stays live even
  // while another tab is showing.
  const intentsFeed = useIntentsFeed();
  // Same reason, plus one more: the feed publishes the open sets' member ids
  // for the canvas marker, and a member node should keep its ring while the
  // user is on another tab.
  const proposalsFeed = useProposalSetsFeed(workspaceSlug);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [cads, setCads] = useState<CadModel[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceListEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [documentsLoaded, setDocumentsLoaded] = useState(false);

  const canvasSlug = useCanvasStore((s) => s.slug);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const sources = useMemo(
    () => canvasSlug === workspaceSlug ? canvasSources(nodes, edges) : [],
    [canvasSlug, workspaceSlug, nodes, edges],
  );

  const openPdf = useUiStore((s) => s.openPdf);
  const openSourceRef = useOpenSourceRef(workspaceSlug);
  // Bring the References tab forward when a reference becomes active (e.g. the
  // user clicked its green box in the PDF viewer), so the selection is visible.
  const activeReferenceId = useUiStore((s) => s.activeReferenceId);
  useEffect(() => {
    if (activeReferenceId) setTab("references");
  }, [activeReferenceId]);
  // The active document is whatever the shared viewer currently shows.
  const activeSlug = useUiStore((s) => s.pdfViewer?.slug ?? null);
  const activePage = useUiStore((s) => s.pdfViewer?.page);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [d, c, w] = await Promise.all([
          documents.list().then(
            (items) => ({ items, error: null }),
            () => ({ items: [] as DocumentSummary[], error: "Could not load project documents." }),
          ),
          cad.list().catch(() => [] as CadModel[]),
          canvases.list().catch(() => [] as WorkspaceListEntry[]),
        ]);
        if (!cancelled) {
          if (!d.error) setDocs(d.items);
          setDocumentsError(d.error);
          setDocumentsLoaded(true);
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

  const openSource = (source: CanvasSource) => {
    const ui = useUiStore.getState();
    if (ui.pdfViewer?.slug === source.slug && ui.pdfViewer.workspaceSlug === workspaceSlug) {
      // Selecting the active source keeps the page and highlight being reviewed.
      ui.setPdfViewerMode("dock");
      ui.pinPdfViewer();
      return;
    }
    if (source.ref) {
      ui.setPdfViewerMode("dock");
      openSourceRef(source.ref);
    } else {
      openDocument(source.slug);
    }
  };

  const visibleCanvases = filterAttachable(workspaces, workspaceSlug);
  const activeDocument = docs.find((d) => d.slug === activeSlug);

  return (
    <div className="flex h-full min-h-0 flex-col bg-white" data-testid="files-explorer">
      {/* Canvas sources and the project-wide file library share the viewer. */}
      <div
        className="flex shrink-0 flex-wrap items-center gap-1 border-b border-neutral-200 bg-neutral-50 px-1.5 py-1"
        role="tablist"
        aria-label="Explorer sections"
      >
        <ExplorerTab
          label="Sources"
          active={tab === "sources"}
          onClick={() => setTab("sources")}
          badge={sources.length}
        />
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
        <ExplorerTab
          label="References"
          active={tab === "references"}
          onClick={() => setTab("references")}
        />
        <ExplorerTab
          label="Intents"
          active={tab === "intents"}
          onClick={() => setTab("intents")}
          badge={intentsFeed.openCount}
        />
        <ExplorerTab
          label="Proposals"
          active={tab === "proposals"}
          onClick={() => setTab("proposals")}
          badge={proposalsFeed.openCount}
        />
      </div>

      {tab === "proposals" ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <ProposalsPanel
            workspaceSlug={workspaceSlug}
            sets={proposalsFeed.sets}
            error={proposalsFeed.error}
          />
        </div>
      ) : tab === "references" ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <ReferencesPanel canvasSlug={workspaceSlug} />
        </div>
      ) : tab === "intents" ? (
        <div className="min-h-0 flex-1 overflow-hidden">
          <IntentsPanel
            workspaceSlug={workspaceSlug}
            open={intentsFeed.open}
            resolved={intentsFeed.resolved}
            error={intentsFeed.error}
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {tab === "sources" ? (
          <div className="space-y-3" data-testid="document-dock">
            <Section title={`Canvas sources (${sources.length})`}>
              {sources.length === 0 ? (
                <Empty hint="Add a source citation to a fact or spec row. Browse Files for project documents." />
              ) : (
                [...sources].sort((a, b) => Number(b.slug === activeSlug) - Number(a.slug === activeSlug))
                  .map((source) => {
                    const doc = docs.find((d) => d.slug === source.slug);
                    return doc ? (
                      <DocumentItem
                        key={source.slug}
                        doc={doc}
                        active={source.slug === activeSlug}
                        expanded={source.slug === activeSlug}
                        page={source.slug === activeSlug ? activePage : undefined}
                        onOpen={() => openSource(source)}
                      />
                    ) : (
                      <MissingDocumentItem
                        key={source.slug}
                        source={source}
                        active={source.slug === activeSlug}
                        hint={!documentsLoaded ? "Loading document details..." : documentsError
                          ? "Document details unavailable" : "Document unavailable in this project"}
                        onOpen={() => openSource(source)}
                      />
                    );
                  })
              )}
            </Section>
            {activeSlug && !sources.some((source) => source.slug === activeSlug) ? (
              <Section title="Open document" subtitle="not cited on this canvas">
                {activeDocument ? (
                  <DocumentItem
                    key={activeSlug}
                    doc={activeDocument}
                    active
                    expanded
                    page={activePage}
                    onOpen={() => openSource({ slug: activeSlug })}
                  />
                ) : (
                  <MissingDocumentItem
                    source={{ slug: activeSlug }}
                    active
                    hint="Document details unavailable"
                    onOpen={() => openSource({ slug: activeSlug })}
                  />
                )}
              </Section>
            ) : null}
          </div>
        ) : tab === "files" ? (
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

        {documentsError && (tab === "sources" || tab === "files") ? (
          <div role="status" className="px-2 pt-2 text-[10px] text-red-600">{documentsError} Retrying automatically.</div>
        ) : null}
        {error ? (
          <div className="px-2 pt-2 text-[10px] text-red-600">error: {error}</div>
        ) : null}
        </div>
      )}
    </div>
  );
}

function ExplorerTab({
  label,
  active,
  onClick,
  badge,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  /** Unread count rendered as a small bubble when > 0 (the Intents tab). */
  badge?: number;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition",
        active
          ? "bg-white text-neutral-900 shadow-sm ring-1 ring-neutral-200"
          : "text-neutral-500 hover:bg-neutral-100",
      )}
    >
      {label}
      {badge != null && badge > 0 ? (
        <span
          data-testid={`tab-badge-${label.toLowerCase()}`}
          className="inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-semibold leading-none text-white"
        >
          {badge > 99 ? "99+" : badge}
        </span>
      ) : null}
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
  expanded = false,
  page,
  onOpen,
}: {
  doc: DocumentSummary;
  active: boolean;
  expanded?: boolean;
  page?: number;
  onOpen: () => void;
}) {
  const [imgError, setImgError] = useState(false);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewImgError, setPreviewImgError] = useState(false);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const thumbnailUrl = documents.pageImageUrl(doc.slug, 1);
  const hint = `${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"} | ${doc.has_gold ? "gold ready" : "no gold"}`;
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
        data-expanded={expanded ? "true" : "false"}
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
                className={cn("flex items-center justify-center rounded bg-neutral-100 text-neutral-400", expanded ? "h-20 w-16" : "h-10 w-8")}
              >
                <FileText size={20} aria-hidden="true" />
              </div>
            ) : (
              <img
                data-testid="thumbnail-img"
                src={thumbnailUrl}
                alt={doc.filename}
                loading="lazy"
                className={cn("rounded object-cover object-top", expanded ? "h-20 w-16" : "h-10 w-8")}
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
            {expanded && page ? (
              <div className="mt-1 text-[10px] font-medium text-sky-700">Viewing page {page}</div>
            ) : null}
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

function MissingDocumentItem({ source, active, hint, onOpen }: {
  source: CanvasSource;
  active: boolean;
  hint: string;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      data-testid="missing-document-item"
      data-slug={source.slug}
      data-active={active ? "true" : "false"}
      aria-current={active ? "true" : undefined}
      onClick={onOpen}
      className={cn("flex w-full items-center gap-2 rounded border px-2 py-2 text-left",
        active ? "border-sky-300 bg-sky-50 ring-1 ring-sky-300" : "border-amber-200 bg-amber-50")}
    >
      <FileText size={20} className="shrink-0 text-neutral-400" aria-hidden="true" />
      <span className="min-w-0">
        <span className="block truncate text-xs font-medium text-neutral-800">{source.slug}</span>
        <span className="block text-[10px] text-neutral-500">{hint}</span>
      </span>
    </button>
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
