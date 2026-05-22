/**
 * Swatches — the swatch grid + Reset / Custom row shared by every chip
 * picker (Fill, Stroke, Text colour). Single shared component so the four
 * places we offer "8 swatches + reset + custom" stay visually identical.
 *
 * The picker patches every selected node with the chosen value. `getColor`
 * is the function that turns a swatch into the colour the picker actually
 * wants — Fill picks `sw.bg`, Stroke and Text pick `sw.stroke`. The visual
 * for each swatch is always its `sw.bg` for fill rows and `sw.stroke` for
 * stroke / text rows.
 */
import { useRef } from "react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";

import type { Swatch } from "./colors";

type Field = "bg_color" | "stroke_color" | "text_color";

type Props = {
  workspaceSlug: string;
  nodeIds: string[];
  getNodeData: (id: string) => Record<string, unknown> | undefined;
  field: Field;
  swatches: Swatch[];
  /** Which colour out of the Swatch to apply. */
  pickFrom: "bg" | "stroke";
  /** Visual flavour — "fill" draws each swatch as a tinted square, "stroke"
   *  draws it as a circle (matches the Miro chip vocabulary). */
  visual: "fill" | "stroke";
  ariaPrefix: string;
  onClose?: () => void;
};

/**
 * Patch a single colour field on every node in `ids`, preserving the rest
 * of `data`. `undefined` removes the override.
 */
async function patchColor(
  workspaceSlug: string,
  ids: string[],
  getNodeData: (id: string) => Record<string, unknown> | undefined,
  field: Field,
  value: string | undefined,
): Promise<void> {
  await Promise.all(
    ids.map(async (id) => {
      // Spread existing data so we don't accidentally wipe label/rows/etc.
      // (the backend reducer REPLACES `data` whole on update).
      const data = { ...(getNodeData(id) ?? {}), [field]: value };
      try {
        await canvases.patchNode(workspaceSlug, id, { data });
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error(`color patch failed for ${id}`, err);
      }
    }),
  );
}

export function Swatches({
  workspaceSlug,
  nodeIds,
  getNodeData,
  field,
  swatches,
  pickFrom,
  visual,
  ariaPrefix,
  onClose,
}: Props) {
  const customRef = useRef<HTMLInputElement | null>(null);
  const apply = (value: string | undefined) => {
    void patchColor(workspaceSlug, nodeIds, getNodeData, field, value).finally(() => {
      onClose?.();
    });
  };
  return (
    <div className="flex flex-col gap-2" data-testid={`swatches-${ariaPrefix}`}>
      <div className="flex flex-wrap items-center gap-1">
        {swatches.map((sw) => (
          <button
            key={`${ariaPrefix}-${sw.label}`}
            type="button"
            role="menuitem"
            aria-label={`${ariaPrefix} ${sw.label}`}
            title={sw.label}
            onClick={() => apply(pickFrom === "bg" ? sw.bg : sw.stroke)}
            className={cn(
              "h-5 w-5 border border-neutral-300 transition hover:scale-110 focus:outline-none focus:ring-2 focus:ring-sky-500",
              visual === "stroke" ? "rounded-full" : "rounded",
            )}
            style={{ background: pickFrom === "bg" ? sw.bg : sw.stroke }}
          />
        ))}
      </div>
      <div className="flex items-center gap-2 text-[11px]">
        <button
          type="button"
          role="menuitem"
          onClick={() => apply(undefined)}
          className="rounded px-1.5 py-0.5 text-neutral-600 hover:bg-neutral-100"
        >
          Reset
        </button>
        <button
          type="button"
          role="menuitem"
          onClick={() => customRef.current?.click()}
          className="rounded px-1.5 py-0.5 text-neutral-600 hover:bg-neutral-100"
        >
          Custom…
        </button>
        <input
          ref={customRef}
          type="color"
          aria-label={`custom ${ariaPrefix} color`}
          className="sr-only"
          onChange={(e) => apply(e.target.value)}
        />
      </div>
    </div>
  );
}
