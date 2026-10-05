/**
 * PresenceStrip — who is on this canvas right now.
 *
 * Renders the live presence roster from the canvas store as small chips in
 * the header: a person icon for humans (SSE viewers like this browser or a
 * monitor window), a robot icon for agents. Agents appear while they are
 * actively writing (the server keeps them on the roster ~90s past their
 * last write) — that is the trust signal this exists for: when nodes move
 * on their own, the strip says who is doing it.
 *
 * The viewer's own entry (matched via the `you` marker from the initial
 * presence event) renders subtly — it is confirmation, not news.
 */
import { Bot, User } from "lucide-react";

import { useCanvasStore } from "@/stores/canvasStore";
import type { PresenceEntry } from "@/realtime/sseClient";

function entryKey(entry: PresenceEntry, index: number): string {
  return entry.client_id ?? `${entry.via}:${entry.kind}:${entry.label ?? ""}:${index}`;
}

function entryTitle(entry: PresenceEntry, isSelf: boolean): string {
  const name = entry.label || entry.kind;
  if (isSelf) return `${name} (you)`;
  if (entry.via === "writes") return `${name} — agent, actively writing`;
  return `${name} — viewing live`;
}

export function PresenceStrip() {
  const presence = useCanvasStore((s) => s.presence);
  const selfId = useCanvasStore((s) => s.presenceSelfId);
  if (presence.length === 0) return null;

  return (
    <div
      className="flex items-center gap-1"
      aria-label="Who is on this canvas right now"
    >
      {presence.map((entry, i) => {
        const isSelf = entry.client_id != null && entry.client_id === selfId;
        const isAgent = entry.kind === "agent";
        const Icon = isAgent ? Bot : User;
        return (
          <span
            key={entryKey(entry, i)}
            title={entryTitle(entry, isSelf)}
            className={
              "flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] " +
              (isSelf
                ? "border-neutral-200 text-neutral-400"
                : isAgent
                  ? "border-violet-300 bg-violet-50 text-violet-700"
                  : "border-emerald-300 bg-emerald-50 text-emerald-700")
            }
          >
            <Icon size={11} aria-hidden />
            <span className="max-w-24 truncate">
              {entry.label || entry.kind}
              {isSelf ? " (you)" : ""}
            </span>
          </span>
        );
      })}
    </div>
  );
}
