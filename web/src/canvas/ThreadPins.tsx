/**
 * ThreadPins — overlay markers for open threads (#344).
 *
 * One marker per distinct anchor: the top-right corner of a thread's
 * targets' bounding box on this canvas, with a count badge when several
 * threads share the anchor. Derived from the shared intents feed (SSE +
 * poll + local nudge) and the workspace store's node geometry; never a
 * node, never written anywhere. Click opens the thread panel (a pin with
 * several threads shows a small picker first).
 *
 * Screen-space fixed positioning, re-projected on pan / zoom / resize by
 * `useFlowToScreen`; markers outside the pane are not drawn so they never
 * float over the source dock or explorer.
 */
import { MessageSquare } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { useIntentsFeed, intentTitle } from "@/shell/intentsFeed";
import { useCanvasStore } from "@/stores/canvasStore";
import { pinsForCanvas, type ThreadPin } from "@/threads/threads";
import { useThreadsStore } from "@/threads/threadsStore";

import { insidePane, useFlowToScreen } from "./useFlowToScreen";

type Props = { workspaceSlug: string };

export function ThreadPins({ workspaceSlug }: Props) {
  const { open } = useIntentsFeed();
  const nodes = useCanvasStore((s) => s.nodes);
  const openThreadId = useThreadsStore((s) => s.openThreadId);
  const openThread = useThreadsStore((s) => s.openThread);
  const { toScreen, paneRect } = useFlowToScreen();
  const [pickerFor, setPickerFor] = useState<string | null>(null);

  const pins = useMemo(
    () => pinsForCanvas(open, workspaceSlug, nodes),
    [open, workspaceSlug, nodes],
  );
  const titles = useMemo(() => {
    const m = new Map<string, string>();
    for (const i of open) m.set(i.id, intentTitle(i));
    return m;
  }, [open]);

  if (pins.length === 0) return null;

  const onPick = (pin: ThreadPin) => {
    if (pin.threadIds.length === 1) {
      openThread(pin.threadIds[0]!);
      setPickerFor(null);
    } else {
      setPickerFor((cur) => (cur === pin.key ? null : pin.key));
    }
  };

  return (
    <>
      {pins.map((pin) => {
        const p = toScreen({ x: pin.x, y: pin.y });
        if (!insidePane(paneRect, p)) return null;
        const active = pin.threadIds.includes(openThreadId ?? "");
        const count = pin.threadIds.length;
        const title = pin.threadIds.map((id) => titles.get(id) ?? id).join("\n");
        return (
          <div
            key={pin.key}
            style={{ position: "fixed", left: p.x, top: p.y, zIndex: 26 }}
            data-testid="thread-pin"
            data-thread-ids={pin.threadIds.join(",")}
            data-count={count}
            onMouseDown={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => onPick(pin)}
              title={title}
              aria-label={count === 1 ? `Open thread: ${title}` : `${count} threads here`}
              className={cn(
                "relative -translate-x-1/2 -translate-y-1/2 rounded-full border bg-white p-1 shadow-md transition hover:bg-amber-50",
                active ? "border-amber-500 text-amber-700" : "border-amber-300 text-amber-600",
              )}
            >
              <MessageSquare className="size-3.5" />
              {count > 1 ? (
                <span
                  data-testid="thread-pin-count"
                  className="absolute -right-1.5 -top-1.5 rounded-full bg-amber-500 px-1 text-[9px] font-semibold leading-3 text-white"
                >
                  {count}
                </span>
              ) : null}
            </button>
            {pickerFor === pin.key ? (
              <div
                role="menu"
                data-testid="thread-pin-picker"
                className="absolute left-2 top-2 min-w-[10rem] max-w-[16rem] rounded-md border border-neutral-200 bg-white p-1 shadow-lg"
              >
                {pin.threadIds.map((id) => (
                  <button
                    key={id}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      openThread(id);
                      setPickerFor(null);
                    }}
                    className="block w-full truncate rounded px-2 py-1 text-left text-[11px] text-neutral-700 hover:bg-neutral-100"
                  >
                    {titles.get(id) ?? id}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </>
  );
}
