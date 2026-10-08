/**
 * CatchUpPanel — "While you were away" (#325, part 4 of #321).
 *
 * When a canvas opens ahead of the viewer's remembered last-seen version
 * (localStorage, see `catchUp.ts`), this panel renders the server-side
 * `canvas_changes` fold: per actor, the net nodes/edges added, updated,
 * and removed since the viewer last looked. Clicking an entry selects and
 * centers that node when it still exists. No replay or scrubbing — the
 * summary is the whole feature.
 *
 * Lifecycle: the decision runs once per canvas visit, the moment the
 * snapshot version lands. First visits (no stored value) record the
 * version silently. After the decision, every version change keeps the
 * stored last-seen fresh, so live edits watched in this tab are never
 * re-announced next time. Dismissing writes the current version and hides
 * the panel.
 *
 * Visual language follows the shell panels (Intents/References): small
 * uppercase headers, bordered rows, neutral palette, dense type.
 */
import { useEffect, useRef, useState } from "react";
import { useReactFlow } from "@xyflow/react";

import {
  canvases,
  type CanvasChanges,
  type ChangeActor,
  type EdgeChangeEntry,
  type NodeChangeEntry,
} from "@/api/canvases";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { readLastSeen, shouldShowCatchUp, writeLastSeen } from "./catchUp";

export function CatchUpPanel({ workspaceSlug }: { workspaceSlug: string }) {
  const slug = useCanvasStore((s) => s.slug);
  const version = useCanvasStore((s) => s.version);
  const [summary, setSummary] = useState<CanvasChanges | null>(null);
  // One decision per canvas visit; live version bumps only refresh storage.
  const decidedFor = useRef<string | null>(null);

  // A different canvas: forget the previous visit's panel state.
  useEffect(() => {
    decidedFor.current = null;
    setSummary(null);
  }, [workspaceSlug]);

  useEffect(() => {
    if (slug !== workspaceSlug || version <= 0) return;
    if (decidedFor.current === slug) {
      // Live edits watched in this tab count as seen.
      writeLastSeen(slug, version);
      return;
    }
    decidedFor.current = slug;
    const lastSeen = readLastSeen(slug);
    if (shouldShowCatchUp(lastSeen, version)) {
      canvases
        .changes(slug, lastSeen as number)
        .then((body) => {
          if (body.groups.length > 0) setSummary(body);
        })
        .catch(() => {});
    }
    writeLastSeen(slug, version);
  }, [slug, workspaceSlug, version]);

  if (!summary) return null;

  const dismiss = () => {
    writeLastSeen(workspaceSlug, useCanvasStore.getState().version);
    setSummary(null);
  };

  return (
    <div
      className="absolute right-3 top-3 z-30 flex max-h-[70%] w-72 flex-col overflow-hidden rounded-md border border-neutral-200 bg-white shadow-lg"
      data-testid="catch-up-panel"
    >
      <div className="flex items-baseline justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          While you were away
        </span>
        <button
          type="button"
          onClick={dismiss}
          className="rounded px-1 text-[10px] text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700"
          title="Dismiss"
          aria-label="Dismiss catch-up panel"
          data-testid="catch-up-dismiss"
        >
          ✕
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-1.5">
        <div className="px-1 text-[9px] italic text-neutral-400">
          v{summary.from_version} → v{summary.to_version}
        </div>
        {summary.groups.map((group, i) => (
          <div
            key={i}
            className="rounded border border-neutral-200 bg-white"
            data-testid="catch-up-group"
          >
            <div className="border-b border-neutral-100 px-2 py-1 text-[10px] font-medium text-neutral-600">
              {actorName(group.actor)}
            </div>
            <div className="px-1 py-1">
              {group.canvas_cleared ? (
                <div className="px-1 py-0.5 text-[11px] text-neutral-600">
                  cleared the canvas
                </div>
              ) : null}
              {group.nodes_added.map((e) => (
                <NodeRow key={`na-${e.id}`} sign="+" tone="text-green-700" entry={e} />
              ))}
              {group.nodes_updated.map((e) => (
                <NodeRow key={`nu-${e.id}`} sign="~" tone="text-amber-700" entry={e} />
              ))}
              {group.nodes_removed.map((e) => (
                <NodeRow key={`nr-${e.id}`} sign="−" tone="text-red-700" entry={e} />
              ))}
              {group.edges_added.map((e) => (
                <EdgeRow key={`ea-${e.id}`} sign="+" tone="text-green-700" entry={e} />
              ))}
              {group.edges_updated.map((e) => (
                <EdgeRow key={`eu-${e.id}`} sign="~" tone="text-amber-700" entry={e} />
              ))}
              {group.edges_removed.map((e) => (
                <EdgeRow key={`er-${e.id}`} sign="−" tone="text-red-700" entry={e} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Display name for a change group's actor; null means pre-attribution. */
export function actorName(actor: ChangeActor | null): string {
  if (!actor) return "earlier";
  return actor.label || actor.kind;
}

function NodeRow({
  sign,
  tone,
  entry,
}: {
  sign: string;
  tone: string;
  entry: NodeChangeEntry;
}) {
  const exists = useCanvasStore((s) => Boolean(s.nodes[entry.id]));
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);
  const { setCenter, getZoom } = useReactFlow();

  const focus = () => {
    const node = useCanvasStore.getState().nodes[entry.id];
    if (!node) return;
    setSelectedNodeId(entry.id);
    void setCenter(
      node.x + (node.width ?? 0) / 2,
      node.y + (node.height ?? 0) / 2,
      { zoom: getZoom(), duration: 400 },
    );
  };

  return (
    <button
      type="button"
      onClick={focus}
      disabled={!exists}
      data-testid="catch-up-node-row"
      data-node-id={entry.id}
      className={cn(
        "flex w-full items-baseline gap-1.5 rounded px-1 py-0.5 text-left text-[11px]",
        exists
          ? "text-neutral-700 hover:bg-neutral-100"
          : "cursor-default text-neutral-400",
      )}
      title={exists ? "Select and center this node" : "No longer on the canvas"}
    >
      <span className={cn("shrink-0 font-mono", tone)} aria-hidden="true">
        {sign}
      </span>
      <span className="min-w-0 truncate">{entry.label || entry.id}</span>
      {entry.node_type ? (
        <span className="ml-auto shrink-0 text-[9px] text-neutral-400">
          {entry.node_type}
        </span>
      ) : null}
    </button>
  );
}

function EdgeRow({
  sign,
  tone,
  entry,
}: {
  sign: string;
  tone: string;
  entry: EdgeChangeEntry;
}) {
  return (
    <div
      className="flex items-baseline gap-1.5 px-1 py-0.5 text-[11px] text-neutral-500"
      data-testid="catch-up-edge-row"
    >
      <span className={cn("shrink-0 font-mono", tone)} aria-hidden="true">
        {sign}
      </span>
      <span className="min-w-0 truncate">
        {entry.label ? `${entry.label} · ` : ""}edge {entry.source} → {entry.target}
      </span>
    </div>
  );
}
