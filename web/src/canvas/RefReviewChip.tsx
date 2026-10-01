import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import {
  cancelTransientClose,
  holdTransientViewer,
} from "@/canvas/transientViewer";
import {
  REF_ACCEPTED_COLOR,
  REF_REJECTED_COLOR,
  refVerdict,
  type RefReview,
  type RefVerdictName,
} from "@/canvas/refReview";

/**
 * RefReviewChip — say whether a reference actually checks out.
 *
 * Checking a reference is already a gesture in this application: hover the
 * anchor, the source appears with the referenced part marked, and you can see
 * for yourself. What was missing was any way to record what you saw, so the
 * next reader -- or the agent that wrote the row -- had to do it all again.
 *
 * Two buttons, not three and a Clear. The state is visible on the button, and
 * pressing the lit one to unset it is the gesture people already use for a
 * toggle. It costs something: a second press takes the note with the verdict,
 * because a reason with no verdict is orphaned. The typed text stays in the
 * field, so a mis-click loses it from storage rather than from the screen.
 *
 * The chip wraps the anchor and owns nothing the anchor already does. The
 * anchor keeps its look and its hover; the verdict is a bare glyph in the
 * icon's bottom corner, so a reference and the verdict on it read as one
 * object. An unjudged reference shows nothing at rest.
 *
 * The menu opens on a right-click on the anchor, as a small dropdown at the
 * pointer. It used to open on the same hover that opens the source, which put
 * a menu over every anchor the pointer crossed -- and near the window's edge,
 * over the anchor itself. Hover is for looking; judging is a deliberate act.
 * Choosing closes it, as choosing does in any menu; so do a click outside and
 * Escape. A note typed before choosing goes with the verdict, and Enter in
 * the note saves it and closes.
 *
 * Keys, while the menu is open: `y` accepts, `n` rejects, and either one
 * pressed again takes the verdict back. Escape dismisses the menu -- it used
 * to clear the verdict, which is a surprising thing for the universal "get me
 * out of here" key to destroy.
 *
 * And it holds the source open for as long as the menu is up. Reaching the
 * menu means leaving the anchor, which is what normally takes a hover-opened
 * pane away. The reader would arrive at the verdict with the evidence already
 * gone, and be asked to judge from memory.
 */


/** The menu's width: w-56 (224px) and its border. */
const MENU_W = 226;

export function RefReviewChip({
  review,
  onChange,
  onRevalidate,
  label,
  children,
}: {
  review: RefReview | null;
  onChange: (state: RefVerdictName | null, note?: string) => void;
  /** Ask the SERVER to re-check the claim against its source, when offered. */
  onRevalidate?: () => void;
  /** What is being judged, for the accessible name. */
  label: string;
  /** The anchor itself. */
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(review?.note ?? "");
  const [rect, setRect] = useState<DOMRect | null>(null);
  const groupRef = useRef<HTMLSpanElement | null>(null);
  const openTimer = useRef<number | null>(null);
  const leaveTimer = useRef<number | null>(null);

  useEffect(() => setNote(review?.note ?? ""), [review?.note]);

  const clearTimer = (t: React.MutableRefObject<number | null>) => {
    if (t.current !== null) window.clearTimeout(t.current);
    t.current = null;
  };
  /** Open at the pointer, the way a context menu does. */
  const showAt = (x: number, y: number) => {
    clearTimer(openTimer);
    clearTimer(leaveTimer);
    setRect(new DOMRect(x, y, 0, 0));
    setOpen(true);
  };
  const stay = () => {
    clearTimer(leaveTimer);
    cancelTransientClose();
  };
  useEffect(
    () => () => {
      clearTimer(openTimer);
      clearTimer(leaveTimer);
    },
    [],
  );

  // A click anywhere but the menu puts it away, as a context menu goes.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest('[data-testid="ref-review-menu"]')) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDown, true);
    return () => document.removeEventListener("mousedown", onDown, true);
  }, [open]);

  // An open menu holds the source. A hold, not a cancel: the next mouse-out
  // anywhere would re-arm the close and the page would go mid-verdict.
  useEffect(() => {
    if (!open) return undefined;
    return holdTransientViewer();
  }, [open]);

  const state = review?.state ?? null;
  const hasNote = Boolean(review?.note);

  // Commit in place. The menu stays: the reader may want to add a note, or
  // change their mind, and leaving is what closes it.
  /**
   * Set the verdict, or take it back by choosing the one already chosen.
   *
   * Two buttons rather than three and a Clear: the state is visible on the
   * button, and pressing the lit one to unset it is the gesture people already
   * use for a toggle. The cost is that a second press also takes the note
   * with it, since a reason with no verdict is orphaned -- so the typed text
   * stays in the field, and one more press puts it back.
   */
  const commit = (next: RefVerdictName) => {
    onChange(state === next ? null : next, next === state ? undefined : note);
    // A choice made is the menu done with, as in any menu. The note typed
    // before choosing goes with the verdict.
    setOpen(false);
  };

  /** Store the note against the verdict it explains, leaving that verdict be. */
  const saveNote = () => {
    if (state) onChange(state, note);
  };

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "y" || e.key === "Y") commit("accepted");
      else if (e.key === "n" || e.key === "N") commit("rejected");
      // Escape dismisses. It used to clear the verdict, which is a surprising
      // thing for the universal "get me out of here" key to destroy.
      else if (e.key === "Escape") setOpen(false);
      else return;
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
    // `commit` closes over the note; re-bind when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, note]);

  return (
    <span
      ref={groupRef}
      data-ref-review=""
      data-testid="ref-review-chip"
      data-state={state ?? "unjudged"}
      className="relative inline-grid h-5 w-5 place-items-center"
      onMouseEnter={() => {
        // Back from the menu: the pane stays.
        cancelTransientClose();
      }}
      onContextMenu={(e) => {
        // Right-click: the verdict menu, at the pointer. The card is not
        // picked out by it; the right button is for the menu alone.
        e.preventDefault();
        e.stopPropagation();
        showAt(e.clientX, e.clientY);
      }}
      onPointerDown={(e) => {
        if (e.button === 2) e.stopPropagation();
      }}
      onMouseDown={(e) => {
        if (e.button === 2) e.stopPropagation();
      }}
    >
      {children}
      {state ? (
        <span
          aria-hidden
          data-testid="ref-review-mark"
          title={
            `${state === "accepted" ? "Checked, right" : "Checked, wrong"}` +
            (review?.note ? ` — ${review.note}` : "")
          }
          className="pointer-events-none absolute bottom-0 right-0 text-[8px] font-bold leading-none"
          style={{ color: state === "accepted" ? REF_ACCEPTED_COLOR : REF_REJECTED_COLOR }}
        >
          {state === "accepted" ? "✓" : "✕"}
          {/* A note gets an underscore beneath the glyph rather than another
              shape beside it. At eight pixels a mark that says "there is more
              to read here" only has to be different, not loud. */}
          {hasNote ? (
            <span
              data-testid="ref-review-has-note"
              className="absolute -bottom-[1px] left-0 h-[1px] w-full rounded-full"
              style={{ background: "currentColor" }}
            />
          ) : null}
        </span>
      ) : null}

      {open && rect
        ? createPortal(
            // Portalled: the row lives inside React Flow's transformed
            // viewport, where a fixed position resolves against the transform
            // and the menu would be scaled by the canvas zoom.
            <div
              data-ref-review=""
              data-testid="ref-review-menu"
              role="menu"
              aria-label={`Source check for ${label}`}
              className="fixed z-50 w-56 overflow-hidden rounded-lg border border-neutral-200 bg-white py-1 text-[12px] text-neutral-800 shadow-xl"
              style={{
                // At the pointer, like any context menu; opening to the left
                // of it when the right has no room, so it never slides back
                // over the anchor it belongs to.
                left:
                  window.innerWidth - (rect.right + 6) >= MENU_W + 8
                    ? rect.right + 6
                    : Math.max(8, rect.left - 6 - MENU_W),
                top: Math.min(rect.top - 2, window.innerHeight - 190),
              }}
              onMouseEnter={stay}
              // The menu is portalled to the page, but React still bubbles its
              // events up through the card it came from: a click on a verdict
              // reached the card and selected it. Nothing in the menu is the
              // card's business.
              onMouseDown={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
              onPointerUp={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
              onDoubleClick={(e) => e.stopPropagation()}
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              onKeyDown={(e) => {
                // Up and down walk the items, as in any menu.
                if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
                const items = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>("[data-menu-item]"),
                );
                const at = items.indexOf(document.activeElement as HTMLElement);
                const next =
                  e.key === "ArrowDown"
                    ? items[(at + 1) % items.length]
                    : items[(at - 1 + items.length) % items.length];
                next?.focus();
                e.preventDefault();
              }}
            >
              <div className="px-3 pb-1 pt-0.5 text-[10px] font-medium uppercase tracking-wide text-neutral-400">
                Source check · {label}
              </div>
              <MenuItem
                testid="ref-review-accept"
                checked={state === "accepted"}
                color={REF_ACCEPTED_COLOR}
                glyph="✓"
                hint="Y"
                onClick={() => commit("accepted")}
              >
                Checked, right
              </MenuItem>
              <MenuItem
                testid="ref-review-reject"
                checked={state === "rejected"}
                color={REF_REJECTED_COLOR}
                glyph="✕"
                hint="N"
                onClick={() => commit("rejected")}
              >
                Checked, wrong
              </MenuItem>
              {state ? (
                <MenuItem
                  testid="ref-review-clear"
                  checked={false}
                  color="rgb(115,115,115)"
                  glyph="○"
                  onClick={() => {
                    onChange(null, undefined);
                    setOpen(false);
                  }}
                  action
                >
                  Not checked yet
                </MenuItem>
              ) : null}
              <div className="my-1 h-px bg-neutral-100" />
              {/* A verdict of "wrong" without "wrong how" leaves the next
                  reader the disagreement and none of the reason. Enter or
                  leaving the field saves it with the current verdict. */}
              <div className="px-2 pb-1">
                <input
                  data-testid="ref-review-note"
                  data-menu-item=""
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  onBlur={() => {
                    if ((review?.note ?? "") !== note.trim()) saveNote();
                  }}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === "Enter") {
                      saveNote();
                      setOpen(false);
                    }
                    if (e.key === "Escape") setOpen(false);
                  }}
                  placeholder={state ? "why? (Enter saves)" : "why? (goes with the verdict you pick)"}
                  className="w-full rounded border border-neutral-200 px-2 py-1 text-[11px] outline-none focus:border-neutral-400"
                />
              </div>
              {/* The reader's verdict and the server's check are different
                  questions. This one asks the machine to look again. */}
              {onRevalidate ? (
                <>
                  <div className="my-1 h-px bg-neutral-100" />
                  <MenuItem
                    testid="ref-review-revalidate"
                    checked={false}
                    color="rgb(115,115,115)"
                    glyph="↻"
                    onClick={() => {
                      onRevalidate();
                      setOpen(false);
                    }}
                    ariaLabel={`Revalidate evidence for ${label}`}
                    action
                  >
                    Re-check against the source
                  </MenuItem>
                </>
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

/**
 * One row of the menu: a glyph, the words, and the key that does the same.
 *
 * The chosen verdict is marked the way menus mark a choice -- tinted, with its
 * glyph in the verdict's colour -- and choosing it again takes it back.
 */
function MenuItem({
  children, onClick, checked, color, testid, glyph, hint, ariaLabel, action = false,
}: {
  children: ReactNode;
  onClick: () => void;
  checked: boolean;
  color: string;
  testid: string;
  glyph: string;
  hint?: string;
  ariaLabel?: string;
  /** An action rather than a choice: a plain menu item, never checked. */
  action?: boolean;
}) {
  return (
    <button
      type="button"
      role={action ? "menuitem" : "menuitemradio"}
      aria-checked={action ? undefined : checked}
      aria-label={ariaLabel}
      data-testid={testid}
      data-menu-item=""
      onClick={onClick}
      className="flex w-full items-center gap-2 px-3 py-1.5 text-left outline-none transition hover:bg-neutral-100 focus:bg-neutral-100"
      style={checked ? { background: `color-mix(in srgb, ${color} 12%, white)` } : undefined}
    >
      <span className="w-3 text-center text-[12px] font-bold" style={{ color }} aria-hidden>
        {glyph}
      </span>
      <span className={`flex-1 ${checked ? "font-medium" : ""}`}>{children}</span>
      {checked ? (
        <span className="text-[10px]" style={{ color }} aria-hidden>
          ●
        </span>
      ) : null}
      {hint ? (
        <kbd className="rounded border border-neutral-200 px-1 font-mono text-[9px] text-neutral-400">{hint}</kbd>
      ) : null}
    </button>
  );
}

/** Re-exported so callers need one import for the chip and its verdict shape. */
export { refVerdict };
