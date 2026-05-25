/**
 * Floating-edge geometry helpers.
 *
 * Computes the point on a node's bounding box where a line from the
 * node's centre to another node's centre exits the box. Combined with
 * the analogous calculation on the target, this gives true "floating"
 * edges: the path connects the nearest perimeter points regardless of
 * which side of each node faces the other.
 *
 * Adapted from the canonical ReactFlow floating-edge example, kept as a
 * standalone helper so both `FloatingEdge` and any future custom edge
 * (orthogonal router, polyline) can share it.
 */
import { Position, type InternalNode, type Node } from "@xyflow/react";

type XY = { x: number; y: number };

/**
 * Find where the segment from node A's centre to node B's centre crosses
 * node A's bounding box. Returns absolute coordinates.
 */
export function getNodeIntersection(
  intersectionNode: InternalNode<Node>,
  targetNode: InternalNode<Node>,
): XY {
  const w = intersectionNode.measured?.width ?? 0;
  const h = intersectionNode.measured?.height ?? 0;
  const ip = intersectionNode.internals.positionAbsolute;
  const tp = targetNode.internals.positionAbsolute;
  const tw = targetNode.measured?.width ?? 0;
  const th = targetNode.measured?.height ?? 0;

  const w2 = w / 2;
  const h2 = h / 2;

  const x2 = ip.x + w2;
  const y2 = ip.y + h2;
  const x1 = tp.x + tw / 2;
  const y1 = tp.y + th / 2;

  const xx1 = (x1 - x2) / (2 * w2) - (y1 - y2) / (2 * h2);
  const yy1 = (x1 - x2) / (2 * w2) + (y1 - y2) / (2 * h2);
  const a = 1 / (Math.abs(xx1) + Math.abs(yy1) || 1);
  const xx3 = a * xx1;
  const yy3 = a * yy1;
  const x = w2 * (xx3 + yy3) + x2;
  const y = h2 * (-xx3 + yy3) + y2;
  return { x, y };
}

/**
 * Pick the nearest side (top/bottom/left/right) of `node`'s box for an
 * intersection point. Used to set `sourcePosition` / `targetPosition` so
 * the bezier control points bow outward in the right direction.
 */
export function getEdgePosition(
  node: InternalNode<Node>,
  intersection: XY,
): Position {
  const n = { ...node.internals.positionAbsolute, ...node };
  const nw = node.measured?.width ?? 0;
  const nh = node.measured?.height ?? 0;
  const nx = Math.round(n.x);
  const ny = Math.round(n.y);
  const px = Math.round(intersection.x);
  const py = Math.round(intersection.y);

  if (px <= nx + 1) return Position.Left;
  if (px >= nx + nw - 1) return Position.Right;
  if (py <= ny + 1) return Position.Top;
  if (py + 1 >= ny + nh) return Position.Bottom;
  return Position.Top;
}

/**
 * Top-level helper: given two ReactFlow internal nodes, return the
 * (sx, sy, tx, ty, sourcePos, targetPos) tuple a custom edge needs.
 */
export function getFloatingEdgeParams(
  source: InternalNode<Node>,
  target: InternalNode<Node>,
): {
  sx: number;
  sy: number;
  tx: number;
  ty: number;
  sourcePos: Position;
  targetPos: Position;
} {
  const sourceIntersect = getNodeIntersection(source, target);
  const targetIntersect = getNodeIntersection(target, source);
  return {
    sx: sourceIntersect.x,
    sy: sourceIntersect.y,
    tx: targetIntersect.x,
    ty: targetIntersect.y,
    sourcePos: getEdgePosition(source, sourceIntersect),
    targetPos: getEdgePosition(target, targetIntersect),
  };
}
