"use client";

import {
  getBezierPath,
  EdgeLabelRenderer,
  type EdgeProps,
} from "@xyflow/react";
import React from "react";

export function AnchoredEdge({
  id,
  markerEnd,
  style,
  label,
  labelStyle,
  labelBgStyle,
  labelBgPadding,
  animated,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
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
