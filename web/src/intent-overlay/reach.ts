import type { Intent } from "./ports";

/**
 * Has any agent seen this remark?
 *
 * The server records the first time an agent's inbox read returned an intent
 * (`seen_at`, `seen_by`). Before that, a remark is either just sent, or old
 * enough that silence means nothing is listening, and the asker should be
 * told so rather than left watching "waiting" forever.
 */
export const UNHEARD_AFTER_S = 30;

export type Reach =
  | { kind: "seen"; by: string; ago: string }
  | { kind: "waiting" }
  | { kind: "unheard" };

/** Who read it, in words: the agent's name, or where it was read from. */
export function readerName(by: Intent["seen_by"]): string {
  if (!by) return "an agent";
  const label = by.label?.trim();
  if (by.kind === "agent") return label || "an agent";
  return label === "cli" ? "the CLI" : label || "someone";
}

function ago(secs: number): string {
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  return `${Math.floor(secs / 86400)} d ago`;
}

export function agentReach(intent: Intent | null | undefined, nowMs: number = Date.now()): Reach {
  const now = nowMs / 1000;
  if (intent?.seen_at) {
    return { kind: "seen", by: readerName(intent.seen_by), ago: ago(Math.max(0, now - intent.seen_at)) };
  }
  if (!intent?.created_at || now - intent.created_at < UNHEARD_AFTER_S) return { kind: "waiting" };
  return { kind: "unheard" };
}
