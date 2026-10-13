import { useEffect, useRef } from "react";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";
import { CONNECT_TOOL, INTENT_TOOL, paletteEntries } from "./registry";

type Args = {
  slug: string;
  active: boolean;
  armedTool: string | null;
  makeSubCanvasSlug: () => string;
  adoptIntoRegion: (id: string, centre: { x: number; y: number }) => Promise<void>;
};

/** Consume one placement while its save and region adoption are pending. */
export function useArmedPlacement(args: Args) {
  const latest = useRef(args); latest.current = args;
  const pending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  return async (flowX: number, flowY: number, size?: { width: number; height: number }) => {
    const current = latest.current;
    const tool = current.armedTool;
    if (!mounted.current || !current.active || pending.current || !tool
      || tool === CONNECT_TOOL || tool === INTENT_TOOL
      || useUiStore.getState().armedTool !== tool || useCanvasStore.getState().slug !== current.slug) return;
    // React state cannot close the gap between two pointer-up events before
    // the first request finishes. Acquire synchronously before any await.
    pending.current = true;
    const isCurrent = () => mounted.current && latest.current.active
      && latest.current.slug === current.slug && useCanvasStore.getState().slug === current.slug
      && latest.current.armedTool === tool && useUiStore.getState().armedTool === tool;
    try {
      if (tool === "canvas") {
        await canvases.createSubCanvas(current.slug, {
          slug: current.makeSubCanvasSlug(), title: "Sub-canvas", x: flowX, y: flowY,
        });
        return;
      }
      const entries = [...paletteEntries("shapes"), ...paletteEntries("cards"), ...paletteEntries("producers")];
      const meta = entries.find((entry) => entry.name === tool)?.meta;
      const width = size?.width ?? meta?.width;
      const height = size?.height ?? meta?.height;
      const response = await canvases.addNode(current.slug, {
        node_type: meta?.nodeType ?? tool,
        label: meta?.noDefaultLabel ? "" : meta?.label ?? "",
        x: flowX, y: flowY,
        ...(width !== undefined ? { width } : {}),
        ...(height !== undefined ? { height } : {}),
        data: { ...(meta?.data ?? {}), ...(width !== undefined ? { width } : {}), ...(height !== undefined ? { height } : {}) },
      });
      const id = (response as { event?: { payload?: { id?: string } } } | null)?.event?.payload?.id;
      if (id && isCurrent()) {
        useUiStore.getState().setSelectedNodeId(id);
        useUiStore.getState().requestInlineRename(id);
        // Regions remain independent; other shapes join the region under
        // their centre using the same size as their saved geometry.
        if (tool !== "area") await current.adoptIntoRegion(id, {
          x: flowX + (width ?? 160) / 2, y: flowY + (height ?? 60) / 2,
        });
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error(tool === "canvas" ? "armed sub-canvas placement failed" : "armed-tool placement failed", error);
    } finally {
      pending.current = false;
      // An earlier save cannot disarm a different tool or another canvas.
      if (isCurrent()) useUiStore.getState().disarmTool();
    }
  };
}
