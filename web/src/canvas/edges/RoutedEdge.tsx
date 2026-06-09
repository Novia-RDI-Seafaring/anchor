/**
 * RoutedEdge — the family of three "Miro-style" routing modes the user
 * can pick from the EdgeContextToolbar: `smooth`, `step`, and `straight`.
 *
 * Unlike FloatingEdge / AnchoredEdge — which auto-route between node
 * perimeters — these consult an explicit list of `data.waypoints` and
 * weave the path through them. With zero waypoints the path is the same
 * as ReactFlow's built-in routers; with waypoints the path becomes a
 * piecewise curve (smooth) or polyline (straight / step) so the user can
 * shape the route.
 *
 *   - `smooth` → SmoothStep with default rounded corners (borderRadius=5).
 *   - `step`   → SmoothStep with `borderRadius=0` so the bends render as
 *                sharp right angles. The Miro screenshot 2 reference.
 *   - `straight` → A polyline through the waypoints. With zero waypoints
 *                  this is a single straight segment.
 *
 * All three share the same Miro-style chip vocabulary (`stroke_color`,
 * `stroke_style`, `start_marker`, `end_marker`) and selected visual.
 */
import {
  BaseEdge,
  EdgeText,
  Position,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

import {
  DEFAULT_EDGE_STROKE,
  SELECTED_EDGE_STROKE,
  resolveEdgeUserStyle,
  userMarkerUrls,
  type Waypoint,
} from "./edge-style";
import {
  EdgeEndpointSockets,
  EvidencePathUnderlay,
  evidenceStroke,
  isActiveEvidence,
  isEvidenceEdge,
} from "./edge-visuals";

type RoutedKind = "smooth" | "step" | "straight";

type RoutedEdgeData = {
  label?: string | null;
  kind?: string | null;
} & Record<string, unknown>;

function buildPath(
  kind: RoutedKind,
  props: {
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    sourcePosition: Position;
    targetPosition: Position;
    waypoints: Waypoint[];
    borderRadius: number;
  },
): { d: string; labelX: number; labelY: number } {
  const { sourceX, sourceY, targetX, targetY, waypoints } = props;
  if (kind === "straight") {
    // Polyline through all waypoints. With none, a straight line.
    const points: Array<{ x: number; y: number }> = [
      { x: sourceX, y: sourceY },
      ...waypoints,
      { x: targetX, y: targetY },
    ];
    const d = points
      .map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x} ${pt.y}`)
      .join(" ");
    const mid = points[Math.floor(points.length / 2)] ?? { x: (sourceX + targetX) / 2, y: (sourceY + targetY) / 2 };
    return { d, labelX: mid.x, labelY: mid.y };
  }
  if (waypoints.length === 0) {
    const [d, lx, ly] = getSmoothStepPath({
      sourceX, sourceY,
      sourcePosition: props.sourcePosition,
      targetX, targetY,
      targetPosition: props.targetPosition,
      borderRadius: props.borderRadius,
    });
    return { d, labelX: lx, labelY: ly };
  }
  // Smooth-step via waypoints: concatenate smooth-step segments between
  // consecutive control points. This is a pragmatic approximation; for
  // the common case (one or two user waypoints) it reads as a clean
  // routed bend.
  const points: Array<{ x: number; y: number }> = [
    { x: sourceX, y: sourceY },
    ...waypoints,
    { x: targetX, y: targetY },
  ];
  let dStr = "";
  let totalMid = { x: 0, y: 0 };
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]!;
    const b = points[i + 1]!;
    const [seg, lx, ly] = getSmoothStepPath({
      sourceX: a.x, sourceY: a.y,
      sourcePosition: Position.Right,
      targetX: b.x, targetY: b.y,
      targetPosition: Position.Left,
      borderRadius: props.borderRadius,
    });
    // Strip the leading M from subsequent segments so the path joins
    // without picking up the pen.
    dStr += i === 0 ? seg : seg.replace(/^M[^MLC]*[MLC]/, (m) => `L ${m.slice(1).split(/\s+/).slice(0, 2).join(" ")} `);
    if (i === Math.floor((points.length - 1) / 2) - (points.length % 2 === 0 ? 1 : 0)) {
      totalMid = { x: lx, y: ly };
    }
  }
  return { d: dStr, labelX: totalMid.x || (sourceX + targetX) / 2, labelY: totalMid.y || (sourceY + targetY) / 2 };
}

function makeRoutedEdge(kind: RoutedKind) {
  return function RoutedEdge(props: EdgeProps) {
    const {
      id,
      sourceX,
      sourceY,
      targetX,
      targetY,
      sourcePosition = Position.Bottom,
      targetPosition = Position.Top,
      data,
      style,
      selected,
    } = props;

    const d = (data ?? {}) as RoutedEdgeData;
    const user = resolveEdgeUserStyle(d);
    const evidence = isEvidenceEdge(d);
    const activeEvidence = isActiveEvidence(d);
    // `step` is "smooth with zero borderRadius"; explicit user override
    // (data.borderRadius) wins so the EdgeContextToolbar can let the
    // user pick a custom corner radius later.
    const defaultRadius = kind === "step" ? 0 : 5;
    const borderRadius = user.borderRadius ?? defaultRadius;

    const { d: path, labelX, labelY } = buildPath(kind, {
      sourceX, sourceY, targetX, targetY,
      sourcePosition, targetPosition,
      waypoints: user.waypoints,
      borderRadius,
    });

    const hasUserCaps = "start_marker" in d || "end_marker" in d;
    const hasUserStrokeStyle = "stroke_style" in d;
    const hasUserStrokeColor = "stroke_color" in d;

    // The routed family doesn't carry SysML markers — that's FloatingEdge
    // / AnchoredEdge territory. We still respect the user-picked caps.
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
      // Default to an arrow at the end so the routed edge has direction.
      const urls = userMarkerUrls({
        start: "none",
        end: "arrow",
        selected: !!selected,
      });
      markerStart = urls.markerStart;
      markerEnd = urls.markerEnd;
    }

    const baseStroke = hasUserStrokeColor
      ? user.strokeColor
      : evidence
        ? evidenceStroke(d)
        : DEFAULT_EDGE_STROKE;
    const baseDasharray = hasUserStrokeStyle ? user.strokeDasharray : undefined;
    const composedStyle: React.CSSProperties = {
      stroke: baseStroke,
      strokeWidth: evidence ? (activeEvidence ? 2.5 : 2) : 1.5,
      ...(style ?? {}),
      strokeDasharray: baseDasharray,
      color: baseStroke,
    };
    if (selected) {
      const selectedStroke = evidence ? evidenceStroke({ ...d, active: true }) : SELECTED_EDGE_STROKE;
      composedStyle.stroke = selectedStroke;
      composedStyle.color = selectedStroke;
      composedStyle.strokeWidth = Number(composedStyle.strokeWidth ?? 1.5) + 0.5;
    }

    const userLabel = (d.label as string | null | undefined) ?? undefined;

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
          sourceX={sourceX}
          sourceY={sourceY}
          targetX={targetX}
          targetY={targetY}
          stroke={String(composedStyle.stroke ?? baseStroke)}
          evidence={evidence}
          active={activeEvidence || !!selected}
        />
        {userLabel ? (
          <EdgeText
            x={labelX}
            y={labelY}
            label={userLabel}
            labelStyle={{ fontSize: 11, fill: "#404040" }}
            labelBgPadding={[4, 2]}
            labelBgBorderRadius={3}
            labelBgStyle={{ fill: "#ffffff", fillOpacity: 0.9 }}
            labelShowBg
          />
        ) : null}
      </>
    );
  };
}

export const SmoothEdge = makeRoutedEdge("smooth");
export const StepEdge = makeRoutedEdge("step");
export const StraightEdge = makeRoutedEdge("straight");
