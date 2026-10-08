/**
 * data.role — the part a card plays in an argument.
 *
 * Mirrors `review.ts`: a small closed vocabulary carried by any element and
 * rendered as a chip, so a reader learns one visual language per canvas
 * instead of decoding whatever colours the author happened to pick.
 *
 * Colour alone would fail a colour-blind reader and fail anyone looking at a
 * zoomed-out board, so each role carries a short WORD as well as a colour.
 * The word is what survives; the colour is the fast path.
 *
 * Keep in step with `anchor/core/workspace/roles.py`.
 */
import type { MaybeData } from "./placeholder";

export const ROLES = [
  "question",
  "criterion",
  "option",
  "evidence",
  "assumption",
  "decision",
  "rejected",
  "open",
] as const;

export type Role = (typeof ROLES)[number];

type RoleStyle = {
  /** Chip label. Short enough to read at a glance, never an icon alone. */
  label: string;
  color: string;
  bg: string;
};

export const ROLE_STYLES: Record<Role, RoleStyle> = {
  question: { label: "question", color: "#3730a3", bg: "#e0e7ff" },
  criterion: { label: "requirement", color: "#1e40af", bg: "#dbeafe" },
  option: { label: "option", color: "#3f3f46", bg: "#f4f4f5" },
  evidence: { label: "evidence", color: "#115e59", bg: "#ccfbf1" },
  assumption: { label: "assumed", color: "#92400e", bg: "#fef3c7" },
  decision: { label: "decision", color: "#166534", bg: "#dcfce7" },
  rejected: { label: "rejected", color: "#64748b", bg: "#f1f5f9" },
  open: { label: "open", color: "#9a3412", bg: "#ffedd5" },
};

export function roleOf(data: MaybeData): Role | null {
  const raw = (data as { role?: unknown } | undefined)?.role;
  return typeof raw === "string" && (ROLES as readonly string[]).includes(raw)
    ? (raw as Role)
    : null;
}

/** A rejected card is still readable, just clearly out of the running. */
export function roleDimmed(data: MaybeData): boolean {
  return roleOf(data) === "rejected";
}
