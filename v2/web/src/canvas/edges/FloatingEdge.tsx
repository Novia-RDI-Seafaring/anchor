import {
  BaseEdge,
  EdgeText,
  Position,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";

import { arrowheadFor, markerUrls, type EdgeMarker } from "./markers";

/**
 * FloatingEdge — generic edge that picks arrowhead/style from `data.marker`.
 *
 * Used for "loose" graph edges that are not anchored to a specific handle
 * on the source/target nodes. The geometry is a bezier; the visual
 * variation comes entirely from `arrowheadFor(data.marker)`.
 *
 * `EdgeMarkerDefs` must be mounted somewhere in the same SVG tree (the
 * canvas root mounts it once) for the marker IDs referenced here to
 * resolve.
 */

type FloatingEdgeData = {
  marker?: EdgeMarker | null;
  label?: string | null;
  source_ref?: Record<string, unknown>;
};

export function FloatingEdge(props: EdgeProps) {
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

  const d = (data ?? {}) as FloatingEdgeData;
  const style_ = arrowheadFor(d.marker);
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

  // Compose stroke from caller `style` + dispatched dasharray. Keep the
  // dispatcher's value as the source of truth for dashing; callers can
  // still override colour/width via `style`.
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
