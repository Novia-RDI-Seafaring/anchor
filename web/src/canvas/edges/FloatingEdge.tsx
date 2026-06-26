import {
  BaseEdge,
  EdgeText,
  getBezierPath,
  useInternalNode,
  type EdgeProps,
} from "@xyflow/react";

import { arrowheadFor, markerUrls, type EdgeMarker } from "./markers";
import {
  DEFAULT_EDGE_STROKE,
  SELECTED_EDGE_STROKE,
  resolveEdgeUserStyle,
  userMarkerUrls,
} from "./edge-style";
import {
  EVIDENCE_EDGE_QUIET_OPACITY,
  EdgeEndpointSockets,
  EvidencePathUnderlay,
  evidenceStroke,
  evidenceStrokeWidth,
  isActiveEvidence,
  isDimmedEvidence,
  isEvidenceEdge,
} from "./edge-visuals";
import { getFloatingEdgeParams } from "./floatingGeometry";

/**
 * FloatingEdge — generic edge that picks arrowhead/style from `data.marker`
 * and computes its endpoints from the *closest perimeter points* of the
 * source and target node boxes (rather than fixed top/bottom handles).
 *
 * That means: wherever you place the nodes, the edge enters from the
 * side that faces the other node — left-of becomes a right-side exit,
 * above becomes a bottom exit, and so on. Standard SysML/UML look.
 *
 * `EdgeMarkerDefs` must be mounted in the same SVG tree (the canvas root
 * mounts it once) for the marker IDs referenced here to resolve.
 *
 * Two parallel styling sources coexist:
 *
 *   1. SysML markers via `data.marker` → `arrowheadFor()` (legacy).
 *   2. User-pickable caps + stroke colour/style via `data.start_marker`,
 *      `data.end_marker`, `data.stroke_color`, `data.stroke_style` from
 *      the Miro-style edge editor (see `edge-style.ts`).
 *
 * When the user picks an explicit cap/style/colour, that wins; otherwise
 * the SysML dispatch still drives the look so existing diagrams render
 * untouched.
 */

type FloatingEdgeData = {
  marker?: EdgeMarker | null;
  label?: string | null;
  source_ref?: Record<string, unknown>;
} & Record<string, unknown>;

export function FloatingEdge(props: EdgeProps) {
  const { id, source, target, data, style, selected } = props;
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);

  if (!sourceNode || !targetNode) return null;

  const { sx, sy, tx, ty, sourcePos, targetPos } = getFloatingEdgeParams(
    sourceNode,
    targetNode,
  );

  const d = (data ?? {}) as FloatingEdgeData;
  const sysml = arrowheadFor(d.marker);
  const user = resolveEdgeUserStyle(d);
  const evidence = isEvidenceEdge(d);
  const activeEvidence = isActiveEvidence(d);

  // A user pick is "explicit" iff the corresponding `data.*` field exists
  // (not just the default fallback). Resolved values always have a non-
  // empty default; we re-check the raw data to know if the user touched
  // the field.
  const hasUserCaps = "start_marker" in d || "end_marker" in d;
  const hasUserStrokeStyle = "stroke_style" in d;
  const hasUserStrokeColor = "stroke_color" in d;

  let markerStart: string | undefined;
  let markerEnd: string | undefined;
  if (hasUserCaps) {
    const urls = userMarkerUrls({
      start: user.startMarker,
      end: user.endMarker,
      selected: !!selected,
    });
    markerStart = urls.markerStart;
    markerEnd = urls.markerEnd;
  } else {
    const urls = markerUrls(sysml);
    markerStart = urls.markerStart;
    markerEnd = urls.markerEnd;
  }

  const userLabel = (d.label as string | null | undefined) ?? undefined;
  const labelText = sysml.labelOverride
    ? userLabel
      ? `${sysml.labelOverride} ${userLabel}`
      : sysml.labelOverride
    : userLabel;

  const [path, labelX, labelY] = getBezierPath({
    sourceX: sx,
    sourceY: sy,
    sourcePosition: sourcePos,
    targetX: tx,
    targetY: ty,
    targetPosition: targetPos,
  });

  // Compose stroke. Precedence:
  //   - `selected` → sky blue (always wins, but `color` keeps the marker
  //      paint matching).
  //   - user-picked `stroke_color` → that colour.
  //   - else → caller-provided style.stroke or the default.
  // For dasharray, user pick beats SysML dispatch (user pick is explicit).
  const baseStroke = hasUserStrokeColor
    ? user.strokeColor
    : evidence
      ? evidenceStroke(d)
      : DEFAULT_EDGE_STROKE;
  const baseDasharray = hasUserStrokeStyle ? user.strokeDasharray : (sysml.strokeDasharray || undefined);
  // Evidence edges render quiet by default and thicken only when active
  // (the hovered node's provenance path, #183). Off-path edges in a hovered
  // bundle carry `data.dimmed` and fade further so the lit path stands out.
  // Style only — width/opacity, never geometry — so hovering can't make an
  // edge jump.
  const composedStyle: React.CSSProperties = {
    stroke: baseStroke,
    strokeWidth: evidence ? evidenceStrokeWidth(activeEvidence) : 1.5,
    // Quiet resting opacity for evidence edges. CanvasGraph owns the
    // stronger off-path `dimmed` fade and passes it via `style.opacity`,
    // which the spread below lets win.
    ...(evidence && !activeEvidence && !isDimmedEvidence(d)
      ? { opacity: EVIDENCE_EDGE_QUIET_OPACITY }
      : {}),
    ...(style ?? {}),
    strokeDasharray: baseDasharray,
    // `color` is what the `currentColor`-based user markers pick up. We
    // multiply with the user's stroke colour so changing the colour
    // repaints the arrowhead/dot to match.
    color: baseStroke,
  };
  if (selected) {
    const selectedStroke = evidence ? evidenceStroke({ ...d, active: true }) : SELECTED_EDGE_STROKE;
    composedStyle.stroke = selectedStroke;
    composedStyle.color = selectedStroke;
    composedStyle.strokeWidth = Number(composedStyle.strokeWidth ?? 1.5) + 0.5;
  }

  return (
    <>
      <EvidencePathUnderlay path={path} evidence={evidence} />
      <BaseEdge
        id={id}
        path={path}
        markerStart={markerStart}
        markerEnd={markerEnd}
        style={composedStyle}
      />
      <EdgeEndpointSockets
        sourceX={sx}
        sourceY={sy}
        targetX={tx}
        targetY={ty}
        stroke={String(composedStyle.stroke ?? baseStroke)}
        evidence={evidence}
        active={activeEvidence || !!selected}
      />
      {labelText ? (
        <EdgeText
          x={labelX}
          y={labelY}
          label={labelText}
          labelStyle={{ fontSize: 11, fill: "#404040" }}
          labelBgPadding={[4, 2]}
          labelBgBorderRadius={3}
          labelBgStyle={{ fill: "#ffffff", fillOpacity: 0.9 }}
          labelShowBg
        />
      ) : null}
    </>
  );
}
