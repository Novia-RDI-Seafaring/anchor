/**
 * colors — shared helpers for the per-node colour & text controls.
 *
 * Three families of `data.*` fields drive the toolbar chips:
 *
 *   - `data.bg_color`     — CSS colour string (`#fef3c7`, `rgb(...)`, `hsl(...)`,
 *                           `transparent`, any named colour). Applied as the
 *                           shape/card background and the AreaNode fill.
 *   - `data.stroke_color` — CSS colour string. Drives the border colour. Also
 *                           feeds the label colour as a fallback when
 *                           `text_color` is unset (preserves the historical
 *                           "tinted shape + tinted label" pairing).
 *   - `data.text_*`       — Optional text overrides. Each is independently
 *                           settable; missing fields fall through to sensible
 *                           defaults. See `resolveText` below.
 *
 * Defaults are deliberately neutral so the chip controls are purely
 * additive — a node with neither field set looks identical to a node that
 * pre-dates the feature.
 *
 * Invalid input (non-string, empty string) falls through to defaults
 * silently. We don't validate CSS syntax: the browser is the final arbiter,
 * and an unknown colour just renders as transparent / inherited.
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

/** Allowed text alignment values. */
export type TextAlign = "left" | "center" | "right";
/** Allowed text size buckets — mapped to rem sizes by `resolveText`. */
export type TextSize = "sm" | "md" | "lg";
/** Allowed font-family slugs — mapped to CSS stacks by `resolveText`. */
export type TextFamily = "default" | "sans" | "serif" | "mono";

/** Resolved text style payload. */
export type ResolvedText = {
  color: string;
  fontWeight: number;
  textAlign: TextAlign;
  fontFamily: string;
  fontSize: string;
};

const FONT_STACKS: Record<TextFamily, string> = {
  // `default` means "let the surrounding stylesheet decide" — emit
  // `inherit` so the primitive's existing cascade is unaffected when the
  // user hasn't picked a family explicitly.
  default: "inherit",
  sans: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  serif: 'ui-serif, Georgia, Cambria, "Times New Roman", Times, serif',
  mono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
};

const SIZE_REMS: Record<TextSize, string> = {
  sm: "0.75rem", // ~12px
  md: "0.875rem", // ~14px
  lg: "1rem", // ~16px
};

const TEXT_ALIGNS: ReadonlySet<TextAlign> = new Set(["left", "center", "right"] as const);

function asAlign(value: unknown, fallback: TextAlign): TextAlign {
  return typeof value === "string" && TEXT_ALIGNS.has(value as TextAlign)
    ? (value as TextAlign)
    : fallback;
}

function asSize(value: unknown, fallback: TextSize): TextSize {
  if (value === "sm" || value === "md" || value === "lg") return value;
  return fallback;
}

function asFamily(value: unknown, fallback: TextFamily): TextFamily {
  if (value === "default" || value === "sans" || value === "serif" || value === "mono") return value;
  return fallback;
}

/**
 * Resolve the effective text styling from a node's `data` payload.
 *
 * - `text_color` falls back to `stroke_color`, then `DEFAULT_STROKE`, so
 *   the historical "label tinted by stroke" behaviour is preserved when
 *   the user hasn't picked an explicit text colour.
 * - `text_bold` is a boolean toggle → 700 vs 400 font-weight.
 * - `text_align` defaults to `"left"` (the natural reading direction;
 *   primitives that historically centred their label can pass their own
 *   default to override).
 * - `text_family` defaults to `"default"` (CSS `inherit`) so existing
 *   styling cascades untouched until the user opts in.
 * - `text_size` defaults to `"md"` (~14px).
 *
 * Callers spread the returned object into the label element's inline style.
 */
export function resolveText(data: MaybeData): ResolvedText {
  const d = (data ?? {}) as Record<string, unknown>;
  const explicit = asColor(d.text_color, "");
  const fallbackStroke = asColor(d.stroke_color, DEFAULT_STROKE);
  const color = explicit || fallbackStroke;
  const fontWeight = d.text_bold === true ? 700 : 400;
  const textAlign = asAlign(d.text_align, "left");
  const family = asFamily(d.text_family, "default");
  const size = asSize(d.text_size, "md");
  return {
    color,
    fontWeight,
    textAlign,
    fontFamily: FONT_STACKS[family],
    fontSize: SIZE_REMS[size],
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

/**
 * Text colour palette — same eight tones as the stroke palette, since
 * Anchor's Style picker pairs label and stroke colours by default. Users
 * can still break the pair via the Text chip.
 */
export const TEXT_SWATCHES: Swatch[] = STROKE_SWATCHES;
