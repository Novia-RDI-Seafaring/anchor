import type { Intent, ThreadItem } from "./ports";

/**
 * Changes the agent applied that the reader has not yet kept or put back.
 *
 * An agent that acts and then resolves its thread is done with its side; the
 * reader is not done with theirs. Resolving is not judging, so an applied
 * change stays on the board with keep and put back until the reader rules
 * on it here or on an earlier visit (`result.kept`).
 */
export function awaitingVerdict(intent: Intent | null | undefined, judged: ReadonlySet<string>): ThreadItem[] {
  if (!intent) return [];
  const kept = new Set(keptIds(intent));
  // A change revised by a later one that is on the canvas stands behind it:
  // the reader judges the revision, and putting that back brings it forward.
  const revised = new Set((intent.items ?? [])
    .filter((item) => item.type === "suggestion" && item.state === "applied" && item.supersedes)
    .map((item) => item.supersedes));
  return (intent.items ?? []).filter((item) =>
    !revised.has(item.id) &&
    item.type === "suggestion" &&
    item.state === "applied" &&
    item.author.kind !== "human" &&
    // A person who approved it has judged it already.
    item.applied_by?.kind !== "human" &&
    !judged.has(item.id) &&
    !kept.has(item.id),
  );
}

/** A change and every applied change it revised: keeping it keeps them all. */
export function revisionChain(intent: Intent | null | undefined, id: string): string[] {
  const items = intent?.items ?? [];
  const chain: string[] = [];
  let at = items.find((item) => item.id === id);
  while (at && !chain.includes(at.id)) {
    chain.push(at.id);
    const back = at.supersedes;
    at = back ? items.find((item) => item.id === back && item.state === "applied") : undefined;
  }
  return chain;
}

/** What was said on the thread after a change landed: the reader's replies and the agent's. */
export function saidSince(intent: Intent | null | undefined, item: ThreadItem): ThreadItem[] {
  return (intent?.items ?? []).filter((it) =>
    it.created_at > item.created_at && !it.place &&
    (it.type === "message" || it.type === "result") && it.text.trim());
}

/** The applied changes the reader kept, as recorded on the thread. */
export function keptIds(intent: Intent): string[] {
  const kept = intent.result?.kept;
  return Array.isArray(kept) ? kept.filter((id): id is string => typeof id === "string") : [];
}

/** Whether a remark still has something for the reader on the board. */
export function stillOnBoard(intent: Intent | null | undefined, judged: ReadonlySet<string>): boolean {
  if (!intent || intent.status !== "resolved") return true;
  if (intent.result?.withdrawn) return false;
  if ((intent.items ?? []).some((item) => item.type === "suggestion" && item.state === "pending")) return true;
  return awaitingVerdict(intent, judged).length > 0;
}
