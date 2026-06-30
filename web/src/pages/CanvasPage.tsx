import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { CanvasGraph } from "@/canvas/CanvasGraph";
import { breadcrumb } from "@/canvas/breadcrumb";
import { PageWithBboxViewer } from "@/canvas/primitives/viewers/PageWithBboxViewer";
import { SourceDock } from "@/canvas/primitives/viewers/SourceDock";
import { CanvasShell } from "@/shell/CanvasShell";

/**
 * CanvasPage — single canvas, with a breadcrumb header that reflects the
 * user's drill-down chain.
 *
 * Breadcrumb behaviour (see `canvas/breadcrumb.ts`):
 *   - When the page mounts and the current `:id` is already in the chain,
 *     truncate the chain to and including this slug (back-navigation).
 *   - When the current `:id` isn't in the chain, reset the chain to a
 *     single entry — this catches "navigated directly from the list page"
 *     and "deep-linked URL" cases.
 *   - When the user clicks "← All canvases" the chain is cleared.
 *   - When the user double-clicks a sub-canvas tile, CanvasGraph calls
 *     `breadcrumb.enter(<sub_slug>)` *before* navigating.
 *
 * Render:
 *   `← All canvases · Plant ▸ Pump loop ▸ <current>`
 *   Each segment except the last is a clickable link routing back.
 */
export function CanvasPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [chain, setChain] = useState<string[]>(() => breadcrumb.chain());

  // Keep the breadcrumb chain in sync with the route. The enter() call in
  // CanvasGraph.onNodeDoubleClick already mutates sessionStorage *before*
  // navigation lands here, so on mount we just re-read.
  useEffect(() => {
    if (!id) return;
    const cur = breadcrumb.chain();
    let next: string[];
    if (cur.includes(id)) {
      // Either we just drilled in (slug at end) or we navigated back to
      // an ancestor — truncate so the chain ends at the current slug.
      const idx = cur.indexOf(id);
      next = cur.slice(0, idx + 1);
      // Persist the truncation so subsequent renders see it.
      if (next.length !== cur.length) {
        breadcrumb.reset(next[0]!);
        next.slice(1).forEach((s) => breadcrumb.enter(s));
      }
    } else {
      // Direct navigation from outside the chain (list page link, deep
      // URL paste). Reset to a single-entry trail.
      next = breadcrumb.reset(id);
    }
    setChain(next);
  }, [id]);

  const onClickAllCanvases = () => {
    breadcrumb.clear();
    setChain([]);
  };

  const trail = useMemo(() => {
    // The rendered crumbs are every entry except the last (which is the
    // current canvas, shown bold below the chevron).
    return chain.slice(0, -1);
  }, [chain]);

  if (!id) return <div className="p-8">Missing canvas id.</div>;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-2">
        <nav className="flex min-w-0 items-center gap-1 text-sm text-neutral-600">
          <Link
            to="/"
            onClick={onClickAllCanvases}
            className="shrink-0 hover:underline"
          >
            ← All canvases
          </Link>
          {trail.map((slug) => (
            <span key={slug} className="flex items-center gap-1 truncate">
              <span className="text-neutral-300">·</span>
              <button
                type="button"
                className="truncate text-neutral-600 hover:underline"
                title={`Back to ${slug}`}
                onClick={() => {
                  // Truncate the chain to and including the clicked slug,
                  // then navigate. The route effect above will run and
                  // confirm the truncation, but we do it eagerly so
                  // there's no flash of stale crumbs.
                  const idx = chain.indexOf(slug);
                  if (idx < 0) return;
                  const next = chain.slice(0, idx + 1);
                  breadcrumb.reset(next[0]!);
                  next.slice(1).forEach((s) => breadcrumb.enter(s));
                  setChain(next);
                  navigate(`/c/${slug}`);
                }}
              >
                {slug}
              </button>
              <span className="text-neutral-300">▸</span>
            </span>
          ))}
        </nav>
        <div className="text-sm font-semibold">{id}</div>
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          <span>drag from the palette · drop a PDF · double-click a document</span>
          <a
            href={`/m/${id}`}
            target="_blank"
            rel="noreferrer"
            className="rounded border border-neutral-300 px-2 py-0.5 hover:bg-neutral-50"
            title="Open this canvas as a standalone read-only monitor in a new window"
          >
            ↗ monitor
          </a>
        </div>
      </header>
      {/* Split-screen: the left-docked source pane (SourceDock) renders
          itself only when the shared viewer is open in "dock" mode, sitting
          to the LEFT of the canvas. Closing the dock returns to canvas-full. */}
      <main className="flex flex-1 overflow-hidden">
        <SourceDock />
        <div className="min-w-0 flex-1">
          <CanvasShell workspaceSlug={id}>
            <CanvasGraph slug={id} />
          </CanvasShell>
        </div>
      </main>
      {/* Legacy modal quick-look (renders only in "modal" mode). */}
      <PageWithBboxViewer />
    </div>
  );
}
