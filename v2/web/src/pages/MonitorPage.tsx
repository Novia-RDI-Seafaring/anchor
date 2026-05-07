/**
 * MonitorPage — the standalone "render-only" projection of a canvas.
 *
 * Architecturally: the monitor is the minimal common denominator across
 * all consumers. It subscribes to SSE and renders state. No palette, no
 * inspector, no commands flowing back. Open in a window, on a wall
 * display, or embed as an iframe — wherever a read-only live view is
 * useful.
 *
 * Routes here at /m/:id. The full interactive UI lives at /c/:id.
 */
import { Link, useParams } from "react-router-dom";

import { CanvasGraph } from "@/canvas/CanvasGraph";

export function MonitorPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return <div className="p-8">Missing canvas id.</div>;
  return (
    <div className="flex h-screen flex-col bg-neutral-50">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-3 py-1.5">
        <Link
          to={`/c/${id}`}
          className="text-xs text-neutral-600 hover:underline"
          title="Open the interactive UI for this canvas"
        >
          ↗ open UI
        </Link>
        <div className="text-xs font-semibold text-neutral-700">
          {id} <span className="font-normal italic text-neutral-400">monitor</span>
        </div>
        <div className="text-[10px] uppercase tracking-wider text-neutral-400">
          read-only
        </div>
      </header>
      <main className="flex-1 overflow-hidden">
        <CanvasGraph slug={id} readOnly />
      </main>
    </div>
  );
}
