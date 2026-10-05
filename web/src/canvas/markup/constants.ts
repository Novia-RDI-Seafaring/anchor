/**
 * CommentLasso  -  marking up the canvas the way a teacher marks an essay.
 *
 * Ring what is wrong, draw a line to a clear patch, write there. The strokes
 * resolve to node ids before anything leaves the browser, so what reaches an
 * agent is "these three nodes, and this sentence" rather than a polyline. The
 * ink is how the reader said it; the ids are what they said it about.
 *
 * The gestures, and why each is shaped this way:
 *
 * A stroke proposes a selection live, so the reader watches a line become a
 * ring rather than finding out when they let go. Rings always select; the
 * FIRST stroke selects whatever its shape. Every other line is just ink, so a
 * connector drawn to a clear patch does not sweep up whatever it crossed.
 *
 * The proposal is meant to be corrected: cmd-click adds or removes a node.
 * Generous-then-fix beats precise-then-fail, because a near miss that caught
 * one node too many costs a click, while one that caught nothing leaves the
 * reader wondering what they did wrong.
 *
 * After a ring catches something, a leader and a cursor are OFFERED at the end
 * of it. A reviewer who has just drawn round a value is about to say why, and
 * making them find a spot and double-click first is a gesture for the tool's
 * benefit rather than theirs. The offer costs nothing when it is wrong:
 * starting anything else withdraws it.
 *
 * Marks queue rather than sending one at a time, because sending each one as
 * it is written would wake the agent once per thought. Queued ink stays on the
 * board, faded: what you have already said should be visible while you decide
 * what to say next.
 *
 * The selection is INERT throughout. It cannot drag, delete or rewire
 * anything, which is what makes it safe to scribble across a board you care
 * about  -  and is the real argument for a mode rather than a chord, alongside
 * the fact that a middle-drag does not exist on a trackpad.
 */

export const NOTE_W = 320;

export const NOTE_H = 110;

export const NOTE_FONT_PX = 26;

/**
 * How far inside a drawn shape its words sit, in flow units.
 *
 * A hand-drawn border is ragged, and text run right up to it collides with the
 * wobble on one line and leaves a gap on the next.
 */
export const HOST_INSET_PX = 10;

/** A resize handle's square, in screen pixels: small, but aimable. */
export const HANDLE_PX = 13;

/**
 * How near a card a line has to stop before it counts as joined to it.
 *
 * A few pixels either side of the edge, because a hand aiming at something
 * stops just short about as often as it stops just inside.
 */
export const SNAP_PX = 10;

/** How far a called-out label stands off the card it belongs to. */
export const CALLOUT_GAP_PX = 40;

/** About a centimetre in from the corner the queue panel rests in. */
export const PANEL_INSET_PX = 40;

/** How far the shape around a remark stands off what it contains. */
export const BLOB_PAD_PX = 46;

/** Clear air between where a leader stops and where its words start. */
export const NOTE_LEAD_GAP_PX = 10;

/** The move tab: wide enough to read as a pull, small enough to stay out of it. */
export const CORNERS = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
] as const;

/** The erase button's box. Thumb-sized, so it can be hit without aiming. */
export const ERASE_PX = 26;

export const INK = "rgb(139, 92, 246)";

/** Size of a ghost node the agent placed without saying how big. */
export const GHOST_W = 220;

export const GHOST_H = 90;

/** How often the board asks after its filed remarks, while it has any. */
export const THREAD_POLL_MS = 2500;

export const PALETTE = [
  { key: "1", name: "violet", ink: "rgb(139, 92, 246)" },
  { key: "2", name: "red", ink: "rgb(220, 38, 38)" },
  { key: "3", name: "orange", ink: "rgb(234, 88, 12)" },
  { key: "4", name: "amber", ink: "rgb(202, 138, 4)" },
  { key: "5", name: "green", ink: "rgb(22, 163, 74)" },
  { key: "6", name: "teal", ink: "rgb(13, 148, 136)" },
  { key: "7", name: "blue", ink: "rgb(37, 99, 235)" },
  { key: "8", name: "pink", ink: "rgb(219, 39, 119)" },
  { key: "9", name: "graphite", ink: "rgb(63, 63, 70)" },
] as const;

export const GHOST_GROUNDS: readonly [string, ...string[]] = [
  "#8a93a6",
  "#c9a86a",
  "#6fa8a0",
  "#b58aa5",
  "#8f9c6b",
  "#a68a7a",
];
