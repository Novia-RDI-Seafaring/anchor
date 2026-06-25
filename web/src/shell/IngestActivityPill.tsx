/**
 * IngestActivityPill — the project-level "N ingesting" surface (issue #51).
 *
 * A compact pill pinned bottom-left of the canvas shell that shows how many
 * documents are ingesting right now, expandable to a per-doc list with stage
 * and a progress bar. It is live for ALL ingests in the project regardless of
 * trigger (web drop, CLI `anchor ingest`, an MCP agent), because it streams the
 * server's durable activity records over SSE.
 *
 * Renders nothing when nothing is ingesting, so it stays out of the way.
 *
 * Sits bottom-left on purpose: ActivityToast owns bottom-right and a future
 * chat input is reserved for centre-bottom (see CanvasShell).
 */
import { useEffect, useMemo, useState } from "react";

import { IngestsSse, type IngestActivity } from "@/realtime/ingestsSse";

/** Human label for a pipeline stage id. Unknown stages pass through. */
const STAGE_LABEL: Record<string, string> = {
  bronze: "reading",
  silver_extract: "extracting",
  silver_index: "indexing",
  silver_render_pages: "rendering",
  silver_polish: "polishing",
  gold_regions: "extracting regions",
  embed: "embedding",
};

function stageLabel(stage: string): string {
  return STAGE_LABEL[stage] ?? stage.replace(/_/g, " ");
}

/** Pure view: given the activity list, render the pill (or nothing). Split out
 *  from the SSE wiring so it is trivial to test. */
export function IngestActivityPillView({ ingests }: { ingests: IngestActivity[] }) {
  const [expanded, setExpanded] = useState(false);

  const running = useMemo(
    () => ingests.filter((i) => i.status === "running"),
    [ingests],
  );
  const failed = useMemo(
    () => ingests.filter((i) => i.status === "failed"),
    [ingests],
  );

  // Nothing happening — render nothing (graceful at zero).
  if (ingests.length === 0) return null;

  const count = running.length;
  const label =
    count > 0
      ? `${count} ingesting`
      : failed.length > 0
        ? `${failed.length} failed`
        : "done";

  return (
    <div className="absolute bottom-4 left-16 z-30 flex flex-col gap-1.5">
      {expanded && (
        <ul className="w-72 rounded-md border border-neutral-200 bg-white/95 p-1.5 shadow-md backdrop-blur">
          {ingests.map((i) => (
            <li key={i.slug} className="px-2 py-1.5">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate font-medium text-neutral-700" title={i.filename || i.slug}>
                  {i.filename || i.slug}
                </span>
                <span
                  className={
                    i.status === "failed"
                      ? "shrink-0 text-red-600"
                      : i.status === "done"
                        ? "shrink-0 text-green-600"
                        : "shrink-0 text-neutral-500"
                  }
                >
                  {i.status === "failed"
                    ? `failed: ${stageLabel(i.stage)}`
                    : i.status === "done"
                      ? "done"
                      : stageLabel(i.stage)}
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
                <div
                  className={
                    i.status === "failed"
                      ? "h-full bg-red-400"
                      : "h-full bg-sky-400 transition-[width]"
                  }
                  style={{ width: `${i.status === "failed" ? 100 : (i.pct ?? 30)}%` }}
                  data-testid={`bar-${i.slug}`}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex items-center gap-2 self-start rounded-full border border-neutral-200 bg-white/95 px-3 py-1.5 text-xs font-medium text-neutral-700 shadow-sm backdrop-blur hover:bg-neutral-50"
        aria-expanded={expanded}
      >
        {count > 0 && (
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-sky-500" />
        )}
        <span>{label}</span>
      </button>
    </div>
  );
}

/** Connected component: subscribes to the ingest-activity SSE stream and feeds
 *  the view. Used in the canvas shell. */
export function IngestActivityPill() {
  const [ingests, setIngests] = useState<IngestActivity[]>([]);

  useEffect(() => {
    const sse = new IngestsSse({ onIngests: setIngests });
    sse.connect();
    return () => sse.disconnect();
  }, []);

  return <IngestActivityPillView ingests={ingests} />;
}
