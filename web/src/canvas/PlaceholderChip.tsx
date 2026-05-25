/**
 * PlaceholderChip — small "✶ empty · <hint>" badge for placeholder nodes.
 *
 * Renders at the top-right corner of a primitive. Italic sky-blue text;
 * unobtrusive but obvious. Agents fill the slot via `canvas_update_node`
 * with `data.placeholder: false`, at which point the parent stops
 * rendering this chip and the dashed outline reverts to the user's stroke.
 */
import { PLACEHOLDER_STROKE } from "./placeholder";

export function PlaceholderChip({ hint }: { hint: string }) {
  return (
    <div
      data-testid="placeholder-chip"
      className="pointer-events-none absolute -top-2.5 right-2 z-10 rounded-full bg-white px-1.5 py-0.5 text-[10px] italic shadow-sm"
      style={{ color: PLACEHOLDER_STROKE, borderColor: PLACEHOLDER_STROKE, borderWidth: 1 }}
    >
      <span aria-hidden>✶</span> empty{hint ? ` · ${hint}` : ""}
    </div>
  );
}
