import { Link, useParams } from "react-router-dom";

import { CanvasGraph } from "@/canvas/CanvasGraph";
import { PageWithBboxViewer } from "@/canvas/primitives/viewers/PageWithBboxViewer";

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
        <div className="text-xs text-neutral-500">
          drop a PDF anywhere · double-click a document to view
        </div>
      </header>
      <main className="flex-1">
        <CanvasGraph slug={id} />
      </main>
      <PageWithBboxViewer />
    </div>
  );
}
