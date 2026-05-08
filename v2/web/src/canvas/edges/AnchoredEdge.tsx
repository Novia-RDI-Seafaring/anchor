import {
  BaseEdge,
  EdgeText,
  Position,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";

import { arrowheadFor, markerUrls, type EdgeMarker } from "./markers";

/**
 * AnchoredEdge — same dispatch as FloatingEdge but attached to specific
 * handles on the source/target nodes (e.g. SysML `interface-connection`
 * edges that target `port-{name}` handles on a block primitive).
 *
 * The geometry is identical to FloatingEdge today (bezier between handle
 * positions). The structural difference is intent: an `anchored` edge in
 * the canvas store carries `sourceHandleId` / `targetHandleId` and a
 * `kind` of "evidence" or "interface-connection". ReactFlow already
 * resolves the handles to coordinates, so we just consume the resolved
 * x/y like FloatingEdge does.
 *
 * Kept as a separate file to make intent legible at the call site
 * (`edgeTypes = { floating: FloatingEdge, anchored: AnchoredEdge }`) and
 * to leave room for divergent geometry later — orthogonal routing for
 * port connections, for example.
 */

type AnchoredEdgeData = {
  marker?: EdgeMarker | null;
  label?: string | null;
  /** "evidence" | "interface-connection" | ... */
  kind?: string | null;
  source_ref?: Record<string, unknown>;
};

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
  } = props;

  const d = (data ?? {}) as AnchoredEdgeData;
  // Anchored edges with no explicit marker default to "interface-connection"
  // (a plain solid line), matching the legacy "evidence" edge appearance.
  const fallback: EdgeMarker = "interface-connection";
  const style_ = arrowheadFor(d.marker ?? fallback);
  const { markerStart, markerEnd } = markerUrls(style_);
  const userLabel = d.label ?? undefined;
  const labelText = style_.labelOverride
    ? userLabel
      ? `${style_.labelOverride} ${userLabel}`
      : style_.labelOverride
    : userLabel;

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const composedStyle: React.CSSProperties = {
    stroke: "#404040",
    strokeWidth: 1.5,
    ...(style ?? {}),
    strokeDasharray: style_.strokeDasharray || undefined,
  };
  if (selected) {
    composedStyle.stroke = "#0284c7";
  }

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerStart={markerStart}
        markerEnd={markerEnd}
        style={composedStyle}
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
