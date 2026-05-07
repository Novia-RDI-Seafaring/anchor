import { Link, useParams } from "react-router-dom";

import { CanvasGraph } from "@/canvas/CanvasGraph";
import { PageWithBboxViewer } from "@/canvas/primitives/viewers/PageWithBboxViewer";
import { CanvasShell } from "@/shell/CanvasShell";

export function CanvasPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return <div className="p-8">Missing canvas id.</div>;
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-2">
        <Link to="/" className="text-sm text-neutral-600 hover:underline">
          ← All canvases
        </Link>
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
      <main className="flex-1 overflow-hidden">
        <CanvasShell workspaceSlug={id}>
          <CanvasGraph slug={id} />
        </CanvasShell>
      </main>
      <PageWithBboxViewer />
    </div>
  );
}
