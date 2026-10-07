import { useUiStore } from "@/stores/uiStore";

/**
 * HoverPreviewToggle — which of the two hover behaviours is live.
 *
 * There are two defensible answers to "what should hovering a source ref do",
 * and arguing about them is slower than trying them:
 *
 *   panel  — a small crop beside the link. Cheap, local, leaves the canvas
 *            where it is. Good when you are reading and want a peek.
 *   viewer — the full source pane fades in on the left and fades away again
 *            on mouse-out, unless you clicked, which pins it. More to look
 *            at, more context, more movement on screen.
 *
 * Both are kept so the same canvas can be judged under each. The choice
 * persists per browser; "panel" is the default because it is the cheaper
 * gesture and the viewer-on-hover is the thing being tried out.
 */
export function HoverPreviewToggle() {
  const mode = useUiStore((s) => s.hoverPreviewMode);
  const setMode = useUiStore((s) => s.setHoverPreviewMode);

  return (
    <div
      className="flex items-center gap-1 rounded border border-neutral-300 px-1 py-0.5"
      role="group"
      aria-label="What hovering a source reference does"
      data-testid="hover-preview-toggle"
    >
      <span className="pr-0.5 text-[10px] uppercase tracking-wide text-neutral-400">
        hover
      </span>
      {(["panel", "viewer"] as const).map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={mode === value}
          data-testid={`hover-mode-${value}`}
          onClick={() => setMode(value)}
          title={
            value === "panel"
              ? "Hovering a source ref shows a small crop beside the link"
              : "Hovering a source ref fades the full source pane in; click to keep it"
          }
          className={`rounded px-1.5 py-0.5 text-[11px] transition ${
            mode === value
              ? "bg-neutral-800 text-white"
              : "text-neutral-500 hover:bg-neutral-100"
          }`}
        >
          {value}
        </button>
      ))}
    </div>
  );
}
