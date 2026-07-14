import { useRef, useState, type PointerEvent } from "react";

import { canvases } from "@/api/canvases";
import {
  PAINT_DRAG_THRESHOLD_PX,
  type PaintRect,
  ghostIsSquare,
  maybeSquareRect,
  paintRectFrom,
} from "@/canvas/paintGeometry";
import { paletteEntries } from "@/canvas/registry";
import { shortId } from "@/canvas/useCanvasDrop";
import { useUiStore } from "@/stores/uiStore";

type FlowPosition = { x: number; y: number };
type ScreenToFlowPosition = (point: FlowPosition) => FlowPosition;

const CAN_SIZE: Record<string, boolean> = {
  concept: true,
  entity: true,
  funnel: true,
  area: true,
};

export function useArmedToolPlacement(
  slug: string,
  screenToFlowPosition: ScreenToFlowPosition,
) {
  const armedTool = useUiStore((state) => state.armedTool);
  const disarmTool = useUiStore((state) => state.disarmTool);
  const pointerDown = useRef<{ clientX: number; clientY: number } | null>(null);
  const [paintRect, setPaintRect] = useState<PaintRect | null>(null);

  const placeNode = async (
    x: number,
    y: number,
    size?: { width: number; height: number },
  ) => {
    if (!armedTool) return;
    if (armedTool === "canvas") {
      try {
        await canvases.createSubCanvas(slug, {
          slug: `${slug}-sub-${shortId()}`,
          title: "Sub-canvas",
          x,
          y,
        });
      } catch (error) {
        console.error("armed sub-canvas placement failed", error);
      } finally {
        disarmTool();
      }
      return;
    }

    const entry = [
      ...paletteEntries("shapes"),
      ...paletteEntries("cards"),
      ...paletteEntries("producers"),
    ].find((candidate) => candidate.name === armedTool);
    const meta = entry?.meta;
    const label = meta?.noDefaultLabel ? "" : meta?.label ?? "";
    const width = size?.width ?? meta?.width;
    const height = size?.height ?? meta?.height;
    try {
      await canvases.addNode(slug, {
        node_type: armedTool,
        label,
        x,
        y,
        ...(width !== undefined ? { width } : {}),
        ...(height !== undefined ? { height } : {}),
        data: {
          ...(meta?.data ?? {}),
          ...(width !== undefined ? { width } : {}),
          ...(height !== undefined ? { height } : {}),
        },
      });
    } catch (error) {
      console.error("armed-tool placement failed", error);
    } finally {
      disarmTool();
    }
  };

  const onPointerDown = (event: PointerEvent) => {
    if (!armedTool) return;
    if ((event.target as HTMLElement).closest(".react-flow__node")) return;
    pointerDown.current = { clientX: event.clientX, clientY: event.clientY };
    setPaintRect(null);
  };

  const onPointerMove = (event: PointerEvent) => {
    const down = pointerDown.current;
    if (!down || !armedTool || !CAN_SIZE[armedTool]) return;
    const raw = paintRectFrom(
      { x: down.clientX, y: down.clientY },
      { x: event.clientX, y: event.clientY },
    );
    setPaintRect(maybeSquareRect(
      raw,
      { x: down.clientX, y: down.clientY },
      ghostIsSquare(armedTool),
    ));
  };

  const onPointerUp = (event: PointerEvent) => {
    if (!armedTool) return;
    const down = pointerDown.current;
    pointerDown.current = null;
    setPaintRect(null);
    if (!down) return;

    const distance = Math.hypot(event.clientX - down.clientX, event.clientY - down.clientY);
    if (distance < PAINT_DRAG_THRESHOLD_PX || !CAN_SIZE[armedTool]) {
      const flow = screenToFlowPosition({ x: down.clientX, y: down.clientY });
      void placeNode(flow.x, flow.y);
      return;
    }

    const raw = paintRectFrom(
      { x: down.clientX, y: down.clientY },
      { x: event.clientX, y: event.clientY },
    );
    const screen = maybeSquareRect(
      raw,
      { x: down.clientX, y: down.clientY },
      ghostIsSquare(armedTool),
    );
    const topLeft = screenToFlowPosition({ x: screen.left, y: screen.top });
    const bottomRight = screenToFlowPosition({
      x: screen.left + screen.width,
      y: screen.top + screen.height,
    });
    void placeNode(topLeft.x, topLeft.y, {
      width: Math.max(40, Math.abs(bottomRight.x - topLeft.x)),
      height: Math.max(24, Math.abs(bottomRight.y - topLeft.y)),
    });
  };

  return {
    armedTool,
    paintRect,
    pointerHandlers: { onPointerDown, onPointerMove, onPointerUp },
  };
}
