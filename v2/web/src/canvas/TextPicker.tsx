/**
 * TextPicker — single-level panel that patches the `data.text_*` family:
 *
 *   - `text_color`  — colour swatch grid + Reset + Custom.
 *   - `text_bold`   — Normal / Bold toggle.
 *   - `text_align`  — Left / Center / Right buttons.
 *   - `text_family` — dropdown: Default / Sans / Serif / Mono.
 *   - `text_size`   — S / M / L buttons.
 *
 * Each control fires a PATCH per selected node, spreading the existing
 * `data` so the rest of the payload survives. The picker is intentionally
 * non-closing for the toggles (Bold / Align / Family / Size) — the user
 * typically tweaks several at once — but the colour swatches close the
 * popover like the Fill / Stroke pickers do.
 */
import { AlignCenter, AlignLeft, AlignRight, Bold } from "lucide-react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";

import { TEXT_SWATCHES, type TextAlign, type TextFamily, type TextSize } from "./colors";
import { Swatches } from "./Swatches";

type Props = {
  workspaceSlug: string;
  nodeIds: string[];
  getNodeData: (id: string) => Record<string, unknown> | undefined;
  onClose?: () => void;
};

async function patchField(
  workspaceSlug: string,
  ids: string[],
  getNodeData: (id: string) => Record<string, unknown> | undefined,
  field: string,
  value: unknown,
): Promise<void> {
  await Promise.all(
    ids.map(async (id) => {
      const data = { ...(getNodeData(id) ?? {}), [field]: value };
      try {
        await canvases.patchNode(workspaceSlug, id, { data });
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error(`text patch failed for ${id}`, err);
      }
    }),
  );
}

export function TextPicker({ workspaceSlug, nodeIds, getNodeData, onClose }: Props) {
  // Read the first selected node's values as the "current" state for the
  // toolbar toggles. Multi-select picks the first node — same convention as
  // the rest of the toolbar (Organize, Open Viewer).
  const firstData = nodeIds[0] ? getNodeData(nodeIds[0]) ?? {} : {};
  const currentBold = firstData.text_bold === true;
  const currentAlign = (firstData.text_align as TextAlign | undefined) ?? "left";
  const currentFamily = (firstData.text_family as TextFamily | undefined) ?? "default";
  const currentSize = (firstData.text_size as TextSize | undefined) ?? "md";

  const setBold = (next: boolean) =>
    void patchField(workspaceSlug, nodeIds, getNodeData, "text_bold", next);
  const setAlign = (next: TextAlign) =>
    void patchField(workspaceSlug, nodeIds, getNodeData, "text_align", next);
  const setFamily = (next: TextFamily) =>
    void patchField(workspaceSlug, nodeIds, getNodeData, "text_family", next === "default" ? undefined : next);
  const setSize = (next: TextSize) =>
    void patchField(workspaceSlug, nodeIds, getNodeData, "text_size", next === "md" ? undefined : next);

  return (
    <div data-testid="text-picker" className="flex min-w-[15rem] flex-col gap-3">
      <Section label="Color">
        <Swatches
          workspaceSlug={workspaceSlug}
          nodeIds={nodeIds}
          getNodeData={getNodeData}
          field="text_color"
          swatches={TEXT_SWATCHES}
          pickFrom="stroke"
          visual="stroke"
          ariaPrefix="text"
          onClose={onClose}
        />
      </Section>
      <Section label="Weight">
        <div className="flex items-center gap-1" role="group" aria-label="text weight">
          <ToggleButton
            active={!currentBold}
            onClick={() => setBold(false)}
            ariaLabel="text weight normal"
          >
            <span className="text-[11px]">Normal</span>
          </ToggleButton>
          <ToggleButton
            active={currentBold}
            onClick={() => setBold(true)}
            ariaLabel="text weight bold"
          >
            <Bold className="size-3.5" />
          </ToggleButton>
        </div>
      </Section>
      <Section label="Align">
        <div className="flex items-center gap-1" role="group" aria-label="text align">
          <ToggleButton
            active={currentAlign === "left"}
            onClick={() => setAlign("left")}
            ariaLabel="text align left"
          >
            <AlignLeft className="size-3.5" />
          </ToggleButton>
          <ToggleButton
            active={currentAlign === "center"}
            onClick={() => setAlign("center")}
            ariaLabel="text align center"
          >
            <AlignCenter className="size-3.5" />
          </ToggleButton>
          <ToggleButton
            active={currentAlign === "right"}
            onClick={() => setAlign("right")}
            ariaLabel="text align right"
          >
            <AlignRight className="size-3.5" />
          </ToggleButton>
        </div>
      </Section>
      <Section label="Family">
        <select
          aria-label="text family"
          value={currentFamily}
          onChange={(e) => setFamily(e.target.value as TextFamily)}
          className="w-full rounded border border-neutral-300 bg-white px-1.5 py-1 text-[12px] outline-none focus:border-neutral-500"
        >
          <option value="default">Default</option>
          <option value="sans">Sans</option>
          <option value="serif">Serif</option>
          <option value="mono">Mono</option>
        </select>
      </Section>
      <Section label="Size">
        <div className="flex items-center gap-1" role="group" aria-label="text size">
          <ToggleButton active={currentSize === "sm"} onClick={() => setSize("sm")} ariaLabel="text size small">
            <span className="text-[10px]">S</span>
          </ToggleButton>
          <ToggleButton active={currentSize === "md"} onClick={() => setSize("md")} ariaLabel="text size medium">
            <span className="text-[11px]">M</span>
          </ToggleButton>
          <ToggleButton active={currentSize === "lg"} onClick={() => setSize("lg")} ariaLabel="text size large">
            <span className="text-[12px]">L</span>
          </ToggleButton>
        </div>
      </Section>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="px-0.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      {children}
    </div>
  );
}

function ToggleButton({
  active, onClick, ariaLabel, children,
}: {
  active: boolean;
  onClick: () => void;
  ariaLabel: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={active}
      aria-label={ariaLabel}
      onClick={onClick}
      className={cn(
        "inline-flex h-6 min-w-6 items-center justify-center rounded border px-1.5 transition focus:outline-none focus:ring-2 focus:ring-sky-500",
        active
          ? "border-sky-300 bg-sky-50 text-sky-700"
          : "border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100",
      )}
    >
      {children}
    </button>
  );
}
