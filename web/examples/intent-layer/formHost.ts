import { useCallback, useLayoutEffect, useState } from "react";
import type { RefObject } from "react";
import type { OverlayHost, Preview, ThreadItem } from "../../src/intent-overlay";
import { measureTargets, type DomTarget } from "./metadata";
import type { FormState } from "./transport";

const viewport = { x: 0, y: 0, zoom: 1 };
export function previewFields(item: ThreadItem, targets: DomTarget[], fields: FormState["fields"]): Preview | null {
  const changes = new Map<string, string>();
  for (const raw of item.ops ?? []) {
    const payload = raw.payload as { field?: unknown; value?: unknown } | undefined;
    if (raw.type !== "FieldSet" || !payload) continue;
    if (payload.field === "email" && typeof payload.value === "string") changes.set("email", payload.value);
    if (payload.field === "max_flow" && typeof payload.value === "number" && Number.isFinite(payload.value)) {
      changes.set("max_flow", String(payload.value));
    }
  }
  const nodes = targets.flatMap((target) => {
    const value = changes.get(target.id);
    if (value === undefined) return [];
    const before = String(fields[target.id as keyof typeof fields] ?? "");
    return [{ ...target.box, kind: "updated" as const, label: target.label,
      rows: [{ key: "Value", value }], before: { label: target.label, rows: [{ key: "Value", value: before }] } }];
  });
  return nodes.length ? { nodes, edges: [] } : null;
}

export function useFormHost(surface: RefObject<HTMLElement | null>, state: FormState,
  thread: OverlayHost["thread"]): { host: OverlayHost; targets: DomTarget[] } {
  const [targets, setTargets] = useState<DomTarget[]>([]);
  const measure = useCallback(() => {
    if (surface.current) setTargets(measureTargets(surface.current, import.meta.env.DEV));
  }, [surface]);
  useLayoutEffect(() => {
    measure();
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(measure);
    if (surface.current) observer?.observe(surface.current);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure, state.revision, surface]);
  return {
    targets,
    host: {
      geometry: {
        boxes: targets.map((target) => target.box), viewport,
        getViewport: () => viewport, setViewport: () => undefined,
        screenToWorld: (point) => {
          const origin = surface.current?.getBoundingClientRect();
          return { x: point.x - (origin?.left ?? 0), y: point.y - (origin?.top ?? 0) };
        },
        rowsOf: () => null, edgesOf: () => [],
      },
      display: {
        labelOf: (id) => targets.find((target) => target.id === id)?.label ?? id,
        preview: (item) => previewFields(item, targets, state.fields),
      },
      thread,
    },
  };
}
