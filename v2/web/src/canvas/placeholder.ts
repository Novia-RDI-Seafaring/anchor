/**
 * placeholder.ts — shared helpers for the "this slot is empty, agent please
 * fill it" affordance.
 *
 * A placeholder node carries:
 *   - `data.placeholder: true` — the flag itself
 *   - `data.placeholder_hint: "<short string>"` — optional UX hint
 *
 * Both visual (dashed sky outline + chip) and agent (`canvas_list_placeholders`
 * MCP tool) read these two fields. When the agent fills the slot it calls
 * `canvas_update_node` with `data.placeholder: false` and a `source_ref`;
 * the chip vanishes and the dashed outline reverts to the user's stroke.
 *
 * Keeping the logic here in one tiny module avoids drift across the four
 * primitives (Concept, Fact, Note, Spec/Table) that opt in.
 */
export type MaybeData = Record<string, unknown> | undefined | null;

export type PlaceholderState = {
  active: boolean;
  hint: string;
};

/** Read placeholder state from a node's `data` payload. */
export function placeholderState(data: MaybeData): PlaceholderState {
  const d = (data ?? {}) as Record<string, unknown>;
  const active = d.placeholder === true;
  const rawHint = d.placeholder_hint;
  const hint = typeof rawHint === "string" ? rawHint : "";
  return { active, hint };
}

/** Sky-100 tint used for the placeholder background fill. */
export const PLACEHOLDER_BG = "rgba(224, 242, 254, 0.6)"; // sky-100 @ 60%
/** Sky-500 for the dashed outline and the chip. */
export const PLACEHOLDER_STROKE = "rgb(14, 165, 233)";
