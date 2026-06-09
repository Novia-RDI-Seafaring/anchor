import {
  BaseEdge,
  EdgeText,
  Position,
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
  EdgeEndpointSockets,
  EvidencePathUnderlay,
  evidenceStroke,
  isActiveEvidence,
  isEvidenceEdge,
} from "./edge-visuals";
import { getEdgePosition, getNodeIntersectionFromPoint } from "./floatingGeometry";

/**
 * AnchoredEdge — same dispatch as FloatingEdge but attached to specific
 * handles on the source/target nodes (e.g. SysML `interface-connection`
 * edges that target `port-{name}` handles on a block primitive).
 *
 * Two parallel styling sources, same as FloatingEdge:
 *   1. SysML markers via `data.marker` (legacy).
 *   2. User-pickable caps + stroke colour/style (Miro-style edge editor).
 *
 * Kept as a separate file to leave room for divergent geometry later —
 * orthogonal routing for port connections, for example.
 */

type AnchoredEdgeData = {
  marker?: EdgeMarker | null;
  label?: string | null;
  /** "evidence" | "interface-connection" | ... */
  kind?: string | null;
  source_ref?: Record<string, unknown>;
} & Record<string, unknown>;

export function AnchoredEdge(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition = Position.Right,
    targetPosition = Position.Left,
    data,
    style,
    selected,
    sourceHandleId,
    targetHandleId,
    target,
  } = props;

  const d = (data ?? {}) as AnchoredEdgeData;
  // Anchored edges with no explicit marker default to "interface-connection"
  // (a plain solid line), matching the legacy "evidence" edge appearance.
  const fallback: EdgeMarker = "interface-connection";
  const sysml = arrowheadFor(d.marker ?? fallback);
  const user = resolveEdgeUserStyle(d);
  const evidence = isEvidenceEdge(d);
  const activeEvidence = isActiveEvidence(d);
  const targetNode = useInternalNode(target);

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

  const shouldFloatTarget =
    !evidence
    && !!sourceHandleId?.startsWith("row:")
    && !targetHandleId
    && !!targetNode;

  const targetPoint = shouldFloatTarget && targetNode
    ? getNodeIntersectionFromPoint(targetNode, { x: sourceX, y: sourceY })
    : { x: targetX, y: targetY };
  const resolvedTargetPosition = shouldFloatTarget && targetNode
    ? getEdgePosition(targetNode, targetPoint)
    : targetPosition;

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX: targetPoint.x,
    targetY: targetPoint.y,
    targetPosition: resolvedTargetPosition,
  });

  const baseStroke = hasUserStrokeColor
    ? user.strokeColor
    : evidence
      ? evidenceStroke(d)
      : DEFAULT_EDGE_STROKE;
  const baseDasharray = hasUserStrokeStyle ? user.strokeDasharray : (sysml.strokeDasharray || undefined);
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
        targetX={targetPoint.x}
        targetY={targetPoint.y}
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
