import type { Box } from "../../src/intent-overlay";

export type DomTarget = {
  id: string;
  tag: string;
  label: string;
  box: Box;
  metadata?: { mode: "component" | "dom"; component?: string; source?: { file: string; line: number } };
};
type DebugFiber = { type?: { displayName?: string; name?: string }; return?: DebugFiber;
  _debugSource?: { fileName?: string; lineNumber?: number } };

/** Private React metadata is optional diagnostic context, never identity. */
export function targetMetadata(element: HTMLElement, dev: boolean): DomTarget["metadata"] {
  if (!dev) return undefined;
  const fallback: NonNullable<DomTarget["metadata"]> = { mode: "dom" };
  try {
    const key = Object.keys(element).find((name) => name.startsWith("__reactFiber$"));
    let fiber = key ? (element as unknown as Record<string, DebugFiber>)[key] : undefined;
    for (let depth = 0; fiber && depth < 12; depth++, fiber = fiber.return) {
      const component = fiber.type?.displayName ?? fiber.type?.name;
      const source = fiber._debugSource;
      if (component) return { mode: "component", component,
        ...(source?.fileName && source.lineNumber ? { source: {
          file: source.fileName.split(/[\\/]/).slice(-3).join("/"), line: source.lineNumber,
        } } : {}) };
    }
  } catch { /* Versions without readable Fiber metadata still have stable DOM IDs. */ }
  return fallback;
}

export function measureTargets(surface: HTMLElement, dev: boolean): DomTarget[] {
  const origin = surface.getBoundingClientRect();
  return Array.from(surface.querySelectorAll<HTMLElement>("[data-intent-id]")).map((element) => {
    const rect = element.getBoundingClientRect();
    const id = element.dataset.intentId!;
    return { id, tag: element.tagName.toLowerCase(), label: element.dataset.intentLabel ?? id,
      box: { id, x: rect.left - origin.left, y: rect.top - origin.top, width: rect.width, height: rect.height },
      ...(dev ? { metadata: targetMetadata(element, true) } : {}) };
  });
}
