import { ERASE_PX, HANDLE_PX, INK } from "./constants";


/** The square a mark is sized by, drawn with the same pen as the mark. */
export function SketchSquare() {
  return (
    <svg viewBox="0 0 14 14" width={HANDLE_PX} height={HANDLE_PX} aria-hidden>
      <path
        d="M2.2 2.6 L11.4 1.9 L11.8 11.5 L2.5 11.9 Z"
        fill="white"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * The x that removes a stroke, drawn rather than typed.
 *
 * Everything else on this layer is hand-drawn: fat round-capped strokes in
 * violet, a ring that never quite closes. A crisp grey x in a bordered
 * circle belongs to the application's chrome, and next to the ink it reads as
 * part of the page rather than part of the mark-up. So this is two pen
 * strokes and a ring, off-true on purpose, in the same colour and weight as
 * whatever it is offering to erase.
 */
export function SketchCross() {
  return (
    <svg viewBox="0 0 24 24" width={ERASE_PX} height={ERASE_PX} aria-hidden>
      {/* A pale disc, so the glyph stays legible where it sits on the ink. */}
      <circle cx="12" cy="12" r="10" fill="rgba(255,255,255,0.82)" />
      {/* Drawn round, not stamped: the ends overrun the way a pen does. */}
      <path
        d="M3.4 11.2 C2.6 5.8 6.6 2.2 12.3 2.1 C17.8 2 21.6 5.6 21.5 11.4 C21.4 17.4 17.3 21.4 11.7 21.3 C6.2 21.2 2.5 17.3 3.1 11.9"
        fill="none"
        stroke={INK}
        strokeWidth={1.7}
        strokeOpacity={0.55}
        strokeLinecap="round"
      />
      <path d="M8.2 8.6 L15.9 15.7" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" />
      <path d="M16 8.4 L8.4 15.9" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" />
    </svg>
  );
}
