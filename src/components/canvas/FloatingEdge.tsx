"use client";

import {
  useInternalNode,
  getBezierPath,
  EdgeLabelRenderer,
  type EdgeProps,
  Position,
} from "@xyflow/react";

type NodeInternal = ReturnType<typeof useInternalNode>;

// Find where a line from targetNode center hits the border of intersectionNode
function getNodeIntersection(intersectionNode: NodeInternal, targetNode: NodeInternal) {
  const w = (intersectionNode?.measured?.width ?? 0) / 2;
  const h = (intersectionNode?.measured?.height ?? 0) / 2;
  const pos = intersectionNode?.internals?.positionAbsolute ?? { x: 0, y: 0 };
  const tpos = targetNode?.internals?.positionAbsolute ?? { x: 0, y: 0 };

  const x2 = pos.x + w;
  const y2 = pos.y + h;
  const x1 = tpos.x + (targetNode?.measured?.width ?? 0) / 2;
  const y1 = tpos.y + (targetNode?.measured?.height ?? 0) / 2;

  const xx1 = (x1 - x2) / (2 * w) - (y1 - y2) / (2 * h);
  const yy1 = (x1 - x2) / (2 * w) + (y1 - y2) / (2 * h);
  const a = 1 / (Math.abs(xx1) + Math.abs(yy1));
  const x = w * (a * xx1 + a * yy1) + x2;
  const y = h * (-a * xx1 + a * yy1) + y2;

  return { x, y };
}

function getEdgePosition(node: NodeInternal, point: { x: number; y: number }): Position {
  const nx = node?.internals?.positionAbsolute?.x ?? 0;
  const ny = node?.internals?.positionAbsolute?.y ?? 0;
  const nw = node?.measured?.width ?? 0;
  const nh = node?.measured?.height ?? 0;
  const px = Math.round(point.x);
  const py = Math.round(point.y);

  if (px <= Math.round(nx) + 1) return Position.Left;
  if (px >= Math.round(nx + nw) - 1) return Position.Right;
  if (py <= Math.round(ny) + 1) return Position.Top;
  if (py >= Math.round(ny + nh) - 1) return Position.Bottom;
  return Position.Top;
}

function getEdgeParams(source: NodeInternal, target: NodeInternal) {
  const sp = getNodeIntersection(source, target);
  const tp = getNodeIntersection(target, source);
  return {
    sx: sp.x, sy: sp.y,
    tx: tp.x, ty: tp.y,
    sourcePos: getEdgePosition(source, sp),
    targetPos: getEdgePosition(target, tp),
  };
}

export function FloatingEdge({
  id,
  source,
  target,
  markerEnd,
  style,
  label,
  labelStyle,
  labelBgStyle,
  labelBgPadding,
  animated,
}: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);

  if (!sourceNode || !targetNode) return null;

  const { sx, sy, tx, ty, sourcePos, targetPos } = getEdgeParams(sourceNode, targetNode);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: sx, sourceY: sy, sourcePosition: sourcePos,
    targetX: tx, targetY: ty, targetPosition: targetPos,
  });

  return (
    <>
      <path
        id={id}
        className={`react-flow__edge-path${animated ? " animated" : ""}`}
        d={edgePath}
        markerEnd={markerEnd}
        style={style}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
              ...labelStyle,
            }}
            className="nodrag nopan"
          >
            <span
              style={{
                background: (labelBgStyle as React.CSSProperties)?.fill ?? "#f5f3ff",
                padding: labelBgPadding
                  ? `${(labelBgPadding as [number, number])[1]}px ${(labelBgPadding as [number, number])[0]}px`
                  : "2px 4px",
                borderRadius: 3,
                opacity: (labelBgStyle as React.CSSProperties)?.fillOpacity ?? 1,
              }}
            >
              {label as React.ReactNode}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
