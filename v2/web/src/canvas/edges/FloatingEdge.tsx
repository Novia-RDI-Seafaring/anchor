import {
  BaseEdge,
  EdgeText,
  getBezierPath,
  useInternalNode,
  type EdgeProps,
} from "@xyflow/react";

import { arrowheadFor, markerUrls, type EdgeMarker } from "./markers";
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
 */

type FloatingEdgeData = {
  marker?: EdgeMarker | null;
  label?: string | null;
  source_ref?: Record<string, unknown>;
};

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
  const styleSpec = arrowheadFor(d.marker);
  const { markerStart, markerEnd } = markerUrls(styleSpec);
  const userLabel = d.label ?? undefined;
  const labelText = styleSpec.labelOverride
    ? userLabel
      ? `${styleSpec.labelOverride} ${userLabel}`
      : styleSpec.labelOverride
    : userLabel;

  const [path, labelX, labelY] = getBezierPath({
    sourceX: sx,
    sourceY: sy,
    sourcePosition: sourcePos,
    targetX: tx,
    targetY: ty,
    targetPosition: targetPos,
  });

  // Compose stroke from caller `style` + dispatched dasharray. Dispatcher
  // is the source of truth for dashing; callers can still override
  // colour/width via `style`.
  const composedStyle: React.CSSProperties = {
    stroke: "#404040",
    strokeWidth: 1.5,
    ...(style ?? {}),
    strokeDasharray: styleSpec.strokeDasharray || undefined,
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
