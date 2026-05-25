/**
 * edge-style — single source of truth for the user-pickable edge style
 * fields surfaced by the Miro-style edge editor (EdgeContextToolbar /
 * EdgeContextMenu).
 *
 * The backend stores these as loose strings in `edge.data`:
 *
 *   - `data.stroke_color`  — CSS colour string (defaults to neutral dark).
 *   - `data.stroke_style`  — "solid" | "dashed" | "dotted".
 *   - `data.start_marker`  — "none" | "arrow" | "circle".
 *   - `data.end_marker`    — "none" | "arrow" | "circle".
 *   - `data.borderRadius`  — number (only for the SmoothStep / Step routers).
 *   - `data.locked`        — boolean.
 *   - `data.waypoints`     — Array<{x, y}> in flow coordinates (smooth /
 *                             step / straight routers).
 *
 * Unknown / missing values fall back to sensible defaults so unstyled
 * edges still render exactly as they did pre-feature.
 *
 * The pre-existing SysML `data.marker` system (see `markers.ts`) is left
 * untouched: that's the four-step seam for canonical UML/SysML markers.
 * The Miro chips layer on top — when both are set we let the user picks
 * win, because the user explicitly clicked them.
 */
import { MARKER_IDS } from "./markers";

export type EdgeStrokeStyle = "solid" | "dashed" | "dotted";
export type EdgeCap = "none" | "arrow" | "circle";

export type Waypoint = { x: number; y: number };

export type EdgeUserData = {
  stroke_color?: string;
  stroke_style?: EdgeStrokeStyle;
  start_marker?: EdgeCap;
  end_marker?: EdgeCap;
  borderRadius?: number;
  locked?: boolean;
  waypoints?: Waypoint[];
};

/** Default stroke colour for user-styled edges — Tailwind `neutral-700`. */
export const DEFAULT_EDGE_STROKE = "#404040";
/** Stroke colour while an edge is selected. */
export const SELECTED_EDGE_STROKE = "#0ea5e9"; // sky-500

const DASH_STYLES: Record<EdgeStrokeStyle, string | undefined> = {
  solid: undefined,
  dashed: "6 4",
  dotted: "2 4",
};

type MaybeData = Record<string, unknown> | undefined | null;

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function asEnum<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : undefined;
}

const STROKE_STYLES = ["solid", "dashed", "dotted"] as const;
const CAPS = ["none", "arrow", "circle"] as const;

export function resolveEdgeUserStyle(data: MaybeData): {
  strokeColor: string;
  strokeDasharray: string | undefined;
  strokeStyle: EdgeStrokeStyle;
  startMarker: EdgeCap;
  endMarker: EdgeCap;
  borderRadius: number | undefined;
  locked: boolean;
  waypoints: Waypoint[];
} {
  const d = (data ?? {}) as Record<string, unknown>;
  const strokeColor = asString(d.stroke_color) ?? DEFAULT_EDGE_STROKE;
  const strokeStyle = asEnum(d.stroke_style, STROKE_STYLES) ?? "solid";
  const startMarker = asEnum(d.start_marker, CAPS) ?? "none";
  const endMarker = asEnum(d.end_marker, CAPS) ?? "arrow";
  const borderRadius = typeof d.borderRadius === "number" ? (d.borderRadius as number) : undefined;
  const locked = d.locked === true;
  const waypoints = Array.isArray(d.waypoints)
    ? (d.waypoints as unknown[]).filter(
        (w): w is Waypoint =>
          !!w
          && typeof w === "object"
          && typeof (w as Waypoint).x === "number"
          && typeof (w as Waypoint).y === "number",
      )
    : [];
  return {
    strokeColor,
    strokeDasharray: DASH_STYLES[strokeStyle],
    strokeStyle,
    startMarker,
    endMarker,
    borderRadius,
    locked,
    waypoints,
  };
}

/**
 * Resolve `markerStart` / `markerEnd` URL fragments for the user-pickable
 * caps. `selected=true` swaps in the slightly larger `*-sel` markers so the
 * selected-edge visual reads as bolder.
 */
export function userMarkerUrls(opts: {
  start: EdgeCap;
  end: EdgeCap;
  selected: boolean;
}): { markerStart: string | undefined; markerEnd: string | undefined } {
  const startId = capMarkerId(opts.start, opts.selected);
  const endId = capMarkerId(opts.end, opts.selected);
  return {
    markerStart: startId ? `url(#${startId})` : undefined,
    markerEnd: endId ? `url(#${endId})` : undefined,
  };
}

function capMarkerId(cap: EdgeCap, selected: boolean): string | null {
  if (cap === "none") return null;
  if (cap === "arrow") return selected ? MARKER_IDS.userArrowSel : MARKER_IDS.userArrow;
  if (cap === "circle") return selected ? MARKER_IDS.userCircleSel : MARKER_IDS.userCircle;
  return null;
}
