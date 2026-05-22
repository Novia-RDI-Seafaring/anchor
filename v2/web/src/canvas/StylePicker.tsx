/**
 * StylePicker — the "Style" submenu surfaced from both the right-click
 * NodeContextMenu and the mini-toolbar's ⋮ More overflow.
 *
 * Two pickers stack inside one panel:
 *   - Fill   → patches `data.bg_color`
 *   - Stroke → patches `data.stroke_color` (drives border + label colour)
 *
 * Each picker shows a tight palette of 8 swatches + Reset + Custom…
 * (`<input type="color">`). Clicking a swatch immediately PATCHes every
 * selected node and closes the submenu (caller's `onClose`). Multi-select
 * is fire-and-forget — SSE reconciles the canonical state and the picker
 * doesn't try to optimistic-update.
 *
 * The merge concern: `WorkspaceService.update_node` REPLACES `data` whole
 * (`evt.fields["data"]` → `setattr(node, "data", v)` in the reducer). So
 * the picker must spread the existing `data` and only override the colour
 * key. Without the spread, clicking a swatch would wipe `label`, `rows`,
 * `width`, `height`, etc.
 *
 * `getNodeData` is a caller-supplied lookup — passed in so the picker
 * doesn't need to subscribe to the canvas store directly (which would
 * couple this UI component to the store shape). The caller already has
 * access via `useCanvasStore`.
 */
import { useRef } from "react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";

import { BG_SWATCHES, STROKE_SWATCHES, type Swatch } from "./colors";

type Props = {
  workspaceSlug: string;
  nodeIds: string[];
  /** Returns the live `data` payload for the given node id, or undefined. */
  getNodeData: (id: string) => Record<string, unknown> | undefined;
  onClose: () => void;
};

/**
 * Patch a single colour field on every node in `ids`, preserving the rest
 * of `data`. Returns a promise that resolves once every PATCH has settled.
 */
async function patchColor(
  workspaceSlug: string,
  ids: string[],
  getNodeData: (id: string) => Record<string, unknown> | undefined,
  field: "bg_color" | "stroke_color",
  value: string | undefined,
): Promise<void> {
  await Promise.all(
    ids.map(async (id) => {
      // Spread existing data so we don't accidentally wipe label/rows/etc.
      // Setting `undefined` removes the override and the primitive falls back
      // to its built-in default via resolveColors().
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

export function StylePicker({ workspaceSlug, nodeIds, getNodeData, onClose }: Props) {
  const bgCustomRef = useRef<HTMLInputElement | null>(null);
  const strokeCustomRef = useRef<HTMLInputElement | null>(null);

  const apply = (field: "bg_color" | "stroke_color", value: string | undefined) => {
    void patchColor(workspaceSlug, nodeIds, getNodeData, field, value).finally(onClose);
  };

  return (
    <div
      role="menu"
      data-testid="style-picker"
      className="min-w-[14rem] rounded-md border border-neutral-200 bg-white p-2 shadow-lg"
    >
      <Section label="Fill">
        <SwatchRow
          swatches={BG_SWATCHES}
          ariaPrefix="fill"
          onPick={(sw) => apply("bg_color", sw.bg)}
        />
        <RowActions
          onReset={() => apply("bg_color", undefined)}
          onCustom={() => bgCustomRef.current?.click()}
          customRef={bgCustomRef}
          onCustomChange={(v) => apply("bg_color", v)}
          ariaLabel="custom fill color"
        />
      </Section>
      <div className="my-2 h-px bg-neutral-200" aria-hidden />
      <Section label="Stroke / text">
        <SwatchRow
          swatches={STROKE_SWATCHES}
          ariaPrefix="stroke"
          // For stroke, the swatch's stroke field is what we want.
          onPick={(sw) => apply("stroke_color", sw.stroke)}
        />
        <RowActions
          onReset={() => apply("stroke_color", undefined)}
          onCustom={() => strokeCustomRef.current?.click()}
          customRef={strokeCustomRef}
          onCustomChange={(v) => apply("stroke_color", v)}
          ariaLabel="custom stroke color"
        />
      </Section>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className="flex flex-col gap-1.5">{children}</div>
    </div>
  );
}

function SwatchRow({
  swatches, onPick, ariaPrefix,
}: {
  swatches: Swatch[];
  onPick: (sw: Swatch) => void;
  ariaPrefix: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {swatches.map((sw) => (
        <button
          key={`${ariaPrefix}-${sw.label}`}
          type="button"
          role="menuitem"
          aria-label={`${ariaPrefix} ${sw.label}`}
          title={sw.label}
          onClick={() => onPick(sw)}
          className={cn(
            "h-5 w-5 rounded border border-neutral-300 transition hover:scale-110 focus:outline-none focus:ring-2 focus:ring-sky-500",
          )}
          style={{ background: ariaPrefix === "stroke" ? sw.stroke : sw.bg }}
        />
      ))}
    </div>
  );
}

function RowActions({
  onReset, onCustom, customRef, onCustomChange, ariaLabel,
}: {
  onReset: () => void;
  onCustom: () => void;
  customRef: React.RefObject<HTMLInputElement | null>;
  onCustomChange: (value: string) => void;
  ariaLabel: string;
}) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <button
        type="button"
        role="menuitem"
        onClick={onReset}
        className="rounded px-1.5 py-0.5 text-neutral-600 hover:bg-neutral-100"
      >
        Reset
      </button>
      <button
        type="button"
        role="menuitem"
        onClick={onCustom}
        className="rounded px-1.5 py-0.5 text-neutral-600 hover:bg-neutral-100"
      >
        Custom…
      </button>
      {/* Native color picker; hidden but reachable via the Custom… button.
          Using a real <input type="color"> keeps platform UX (eye-dropper,
          colour history) without bringing in a colour-picker dependency. */}
      <input
        ref={customRef}
        type="color"
        aria-label={ariaLabel}
        className="sr-only"
        onChange={(e) => onCustomChange(e.target.value)}
      />
    </div>
  );
}
