/**
 * colors — shared helper for the per-node colour controls.
 *
 * Two `data` fields drive the "Style" submenu (right-click and the
 * mini-toolbar ⋮ More overflow):
 *
 *   - `data.bg_color`     — CSS colour string (`#fef3c7`, `rgb(...)`, `hsl(...)`,
 *                           `transparent`, any named colour). Applied as the
 *                           shape/card background and the AreaNode fill.
 *   - `data.stroke_color` — CSS colour string. Drives the border colour and
 *                           the label text colour in one knob (the way
 *                           draw.io / Figma tint a shape-and-its-label
 *                           together: pastel fill + saturated stroke + matching
 *                           label reads as a single semantic recolour).
 *
 * Defaults are deliberately neutral so the colour controls are purely
 * additive — a node with neither field set looks identical to a node that
 * pre-dates the feature.
 *
 * Invalid input (non-string, empty string) falls through to the defaults
 * silently. We don't validate the CSS syntax itself: the browser is the
 * final arbiter, and an unknown colour just renders as transparent /
 * inherited, which is benign.
 */

/** Default background — `transparent` so each primitive's own bg shows. */
export const DEFAULT_BG = "transparent";

/** Default stroke — Tailwind `neutral-500`. Matches the existing borders
 *  used by ConceptNode, EntityNode, FunnelNode, AreaNode and friends. */
export const DEFAULT_STROKE = "rgb(115, 115, 115)";

type MaybeData = Record<string, unknown> | undefined | null;

function asColor(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  if (!trimmed) return fallback;
  return trimmed;
}

/**
 * Resolve the effective colours from a node's `data` payload.
 *
 * Callers do `const { bg, stroke } = resolveColors(data)` and feed both
 * into inline `style={{ background: bg, borderColor: stroke, color: stroke }}`.
 * The diamond (FunnelNode) also threads `stroke` into its SVG `stroke=` prop.
 */
export function resolveColors(data: MaybeData): { bg: string; stroke: string } {
  const d = data ?? {};
  return {
    bg: asColor((d as Record<string, unknown>).bg_color, DEFAULT_BG),
    stroke: asColor((d as Record<string, unknown>).stroke_color, DEFAULT_STROKE),
  };
}

/**
 * Background swatch palette — pastels chosen to stay legible under the
 * matching saturated stroke. `null` rows are the `Reset` affordance.
 *
 * Each entry pairs a `bg` and the recommended `stroke` so the picker can
 * patch both fields in a single round-trip if the user wants the matched
 * pair, while still allowing them to break the pair via the stroke-only
 * picker. Tones follow Tailwind 100/600 conventions.
 */
export type Swatch = { bg: string; stroke: string; label: string };

export const BG_SWATCHES: Swatch[] = [
  { bg: "#ffffff", stroke: "rgb(82, 82, 82)", label: "White" },
  { bg: "#f1f5f9", stroke: "rgb(71, 85, 105)", label: "Slate" },
  { bg: "#f5f5f4", stroke: "rgb(87, 83, 78)", label: "Stone" },
  { bg: "#fef3c7", stroke: "rgb(202, 138, 4)", label: "Yellow" },
  { bg: "#e0f2fe", stroke: "rgb(2, 132, 199)", label: "Sky" },
  { bg: "#dcfce7", stroke: "rgb(22, 163, 74)", label: "Green" },
  { bg: "#ffe4e6", stroke: "rgb(225, 29, 72)", label: "Rose" },
  { bg: "#ede9fe", stroke: "rgb(124, 58, 237)", label: "Violet" },
];

export const STROKE_SWATCHES: Swatch[] = [
  { bg: "#ffffff", stroke: "rgb(82, 82, 82)", label: "Neutral" },
  { bg: "#f1f5f9", stroke: "rgb(71, 85, 105)", label: "Slate" },
  { bg: "#f5f5f4", stroke: "rgb(87, 83, 78)", label: "Stone" },
  { bg: "#fef3c7", stroke: "rgb(202, 138, 4)", label: "Yellow" },
  { bg: "#e0f2fe", stroke: "rgb(2, 132, 199)", label: "Sky" },
  { bg: "#dcfce7", stroke: "rgb(22, 163, 74)", label: "Green" },
  { bg: "#ffe4e6", stroke: "rgb(225, 29, 72)", label: "Rose" },
  { bg: "#ede9fe", stroke: "rgb(124, 58, 237)", label: "Violet" },
];
