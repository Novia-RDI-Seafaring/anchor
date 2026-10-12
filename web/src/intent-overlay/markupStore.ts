import type { Intent } from "./ports";
import type { Cut } from "./cuts";
import { markHits, pivotStroke, strokeHeading, type Box, type Point } from "./lasso";
import { GHOST_GROUNDS, PALETTE } from "./constants";
import type { Sketch } from "./sketch";
import type { Strike } from "./strikes";
import { createStore } from "zustand/vanilla";
export { GHOST_GROUNDS, PALETTE } from "./constants";

export type Note = {
  id: string;
  x: number;
  y: number;
  text: string;
  /** Written inside a shape that was drawn: the note takes that shape's box. */
  inStroke?: number;
  /** Where the leader that offered this note started. */
  from?: Point;
  /**
   * The words carry on a stroke the reader drew, rather than a leader offered
   * to them, so no separate line is drawn to reach them.
   */
  continues?: boolean;
  /** Which stroke they carry on from, so dragging them can swing it. */
  onStroke?: number;
  /**
   * Which ring they belong to. The line is not stored: it is drawn from that
   * ring's centre to wherever the words are now, clipped at the outline. So
   * carrying the words anywhere keeps the line looking like it comes out of
   * the middle of the ring, with no pivot point left behind on the edge.
   */
  ringStroke?: number;
  /** Offered rather than asked for: it evaporates unless it is used. */
  offered?: boolean;
  /** The pen it was written with. */
  color?: string;
  /**
   * Carried by hand, so the layout leaves it alone.
   *
   * Auto-placed words are positioned by rule, not stored; dragging one is the
   * reader saying they want it exactly there, and a rule that immediately put
   * it back would be arguing with them.
   */
  pinned?: boolean;
};

export type Queued = {
  id: string;
  text: string;
  ids: string[];
  /** The drawing read as nodes and edges, so the agent gets the shape of it. */
  sketch: Sketch;
  /** Lines across tables, read as the row boundary they went through. */
  cuts: Cut[];
  /** Crosses over edges, read as the edge to take away. */
  strikes: Strike[];
  marks: Mark[];
  /** The words as written and placed, so a queued remark still reads as one. */
  notes: Note[];
};

/**
 * One drawn stroke and the pen it was drawn with.
 *
 * Strokes used to be bare geometry, which left nowhere to put a colour. The
 * points stay separate from the colour rather than being mixed into it, so
 * every geometry helper keeps taking plain points and none of them had to
 * learn about pens.
 */
export type Mark = {
  points: Point[];
  color: string;
  /**
   * Drawn from one element and dropped on another: a join rather than a
   * remark. The ids are what an agent reads -- "connect these two" -- and the
   * line is clipped to the edge so it looks joined rather than drawn over.
   */
  link?: { from: string | null; to: string };
};

/**
 * A remark that has been sent, still on the board as a ghost.
 *
 * Filing an intent used to make it vanish, which left the reader looking at
 * a blank canvas and a line of text saying it had gone somewhere. It has not
 * gone anywhere: the agent is about to work on exactly this spot. So the ink
 * stays, faint, and becomes the place where that work shows up -- the
 * agent's progress, its questions, and in the end the proposal to approve.
 */
export type Filed = {
  intentId: string;
  text: string;
  ids: string[];
  sketch: Sketch;
  marks: Mark[];
  notes: Note[];
  /** The pen it was drawn with: the ghost and its status wear the same one. */
  color: string;
  /** The ground it rested on while it was being drawn; the ghost keeps it. */
  ground?: string;
  /** The thread as last fetched. Null until the first poll lands. */
  intent: Intent | null;
};

/**
 * A remark set aside, unsent, while another is being drawn.
 *
 * Several asks can be in the making at once -- one half-drawn while a
 * second comes to mind -- and they must not fold into each other. Each
 * rests on its own ground; a tap on that ground brings it back to the pen.
 */
export type Stack = Queued & { ground: string };

export type Selection = { strokes: number[]; notes: string[] };
export const NOTHING_SELECTED: Selection = { strokes: [], notes: [] };
type Update<T> = T | ((previous: T) => T);

export type MarkupState = {
  marks: Mark[];
  ink: string;
  notes: Note[];
  ids: string[];
  manual: string[] | null;
  hoveredStroke: number | null;
  editing: string | null;
  selected: Selection;
  dropOn: string | null;
  activeLabel: string | null;
  sending: boolean;
  filed: Filed[];
  openFiled: string | null;
  kept: Set<string>;
  lifted: boolean;
  hoverShelf: string | null;
  shelf: Stack[];
  ground: string;
  panelAt: Point | null;
  answering: { item: string; text: string } | null;
  groundSeq: number;
  marginDeg: number | null;
};

type MarkupActions = {
  replaceMarks: (value: Update<MarkupState["marks"]>) => void;
  setInk: (value: Update<MarkupState["ink"]>) => void;
  updateNotes: (value: Update<MarkupState["notes"]>) => void;
  setTargets: (value: Update<MarkupState["ids"]>) => void;
  setManualTargets: (value: Update<MarkupState["manual"]>) => void;
  hoverMark: (value: Update<MarkupState["hoveredStroke"]>) => void;
  editNote: (value: Update<MarkupState["editing"]>) => void;
  selectMarks: (value: Update<MarkupState["selected"]>) => void;
  previewJoin: (value: Update<MarkupState["dropOn"]>) => void;
  selectLabel: (value: Update<MarkupState["activeLabel"]>) => void;
  openThread: (value: Update<MarkupState["openFiled"]>) => void;
  liftPen: (value: Update<MarkupState["lifted"]>) => void;
  hoverStack: (value: Update<MarkupState["hoverShelf"]>) => void;
  movePanel: (value: Update<MarkupState["panelAt"]>) => void;
  writeAnswer: (value: Update<MarkupState["answering"]>) => void;
  setMargin: (value: Update<MarkupState["marginDeg"]>) => void;
  addMark: (mark: Mark) => void;
  keepSuggestion: (id: string) => Set<string>;
  loadFiled: (remarks: Filed[]) => void;
  refreshFiled: (latest: (Intent | null)[]) => void;
  commitNote: (id: string) => void;
  resetRemark: () => void;
  pauseMarkup: () => void;
  dropMarks: (strokes: Iterable<number>, noteIds: Iterable<string>, boxes: Box[]) => void;
  recolour: (color: string) => void;
  moveLabel: (id: string, to: Point, boxes: Box[]) => void;
  newStack: (snapshot: Queued) => void;
  switchStack: (id: string, snapshot: Queued) => void;
  send: (snapshot: Queued, create: () => Promise<Intent>) => Promise<boolean>;
  settle: (intentId: string, judged: Set<string>, host: {
    get: (id: string) => Promise<Intent | null>;
    resolve: (id: string, result: { verdict: string }) => Promise<unknown>;
  }) => Promise<void>;
};

const emptyRemark = () => ({
  marks: [], notes: [], ids: [], manual: null, hoveredStroke: null,
  selected: { strokes: [], notes: [] }, activeLabel: null, dropOn: null, marginDeg: null,
});
const hasRemark = (state: MarkupState) =>
  state.marks.length > 0 || state.notes.some((note) => note.text.trim());

/** One store per mounted overlay. Active toggles retain it; separate overlays never share it. */
export function createMarkupStore() {
  return createStore<MarkupState & MarkupActions>()((set, get) => ({
    marks: [],
    ink: PALETTE[0].ink,
    notes: [],
    ids: [],
    manual: null,
    hoveredStroke: null,
    editing: null,
    selected: { strokes: [], notes: [] },
    dropOn: null,
    activeLabel: null,
    sending: false,
    filed: [],
    openFiled: null,
    kept: new Set(),
    lifted: false,
    hoverShelf: null,
    shelf: [],
    ground: GHOST_GROUNDS[0],
    panelAt: null,
    answering: null,
    groundSeq: 0,
    marginDeg: null,
    replaceMarks: (value) => set((state) => ({ marks: typeof value === "function" ? value(state.marks) : value })),
    setInk: (value) => set((state) => ({ ink: typeof value === "function" ? value(state.ink) : value })),
    updateNotes: (value) => set((state) => ({ notes: typeof value === "function" ? value(state.notes) : value })),
    setTargets: (value) => set((state) => ({ ids: typeof value === "function" ? value(state.ids) : value })),
    setManualTargets: (value) => set((state) => ({ manual: typeof value === "function" ? value(state.manual) : value })),
    hoverMark: (value) => set((state) => ({ hoveredStroke: typeof value === "function" ? value(state.hoveredStroke) : value })),
    editNote: (value) => set((state) => ({ editing: typeof value === "function" ? value(state.editing) : value })),
    selectMarks: (value) => set((state) => ({ selected: typeof value === "function" ? value(state.selected) : value })),
    previewJoin: (value) => set((state) => ({ dropOn: typeof value === "function" ? value(state.dropOn) : value })),
    selectLabel: (value) => set((state) => ({ activeLabel: typeof value === "function" ? value(state.activeLabel) : value })),
    openThread: (value) => set((state) => ({ openFiled: typeof value === "function" ? value(state.openFiled) : value })),
    liftPen: (value) => set((state) => ({ lifted: typeof value === "function" ? value(state.lifted) : value })),
    hoverStack: (value) => set((state) => ({ hoverShelf: typeof value === "function" ? value(state.hoverShelf) : value })),
    movePanel: (value) => set((state) => ({ panelAt: typeof value === "function" ? value(state.panelAt) : value })),
    writeAnswer: (value) => set((state) => ({ answering: typeof value === "function" ? value(state.answering) : value })),
    setMargin: (value) => set((state) => ({ marginDeg: typeof value === "function" ? value(state.marginDeg) : value })),
    keepSuggestion: (id) => {
      const kept = new Set(get().kept).add(id);
      set({ kept });
      return kept;
    },
    loadFiled: (remarks) => set((state) => {
      const have = new Set(state.filed.map((remark) => remark.intentId));
      return { filed: [...state.filed, ...remarks.filter((remark) => !have.has(remark.intentId))] };
    }),
    refreshFiled: (latest) => set((state) => ({
      filed: state.filed.map((remark) => {
        const intent = latest.find((intent) => intent?.id === remark.intentId);
        return intent ? { ...remark, intent } : remark;
      }).filter((remark) => !remark.intent || remark.intent.status !== "resolved" ||
        (remark.intent.items ?? []).some((item) => item.type === "suggestion" && item.state === "pending")),
    })),
    addMark: (mark) => set((state) => ({ marks: [...state.marks, mark] })),
    commitNote: (id) => set((state) => ({
      notes: state.notes.filter((note) => note.id !== id || note.text.trim()),
      editing: state.editing === id ? null : state.editing,
    })),
    resetRemark: () => set(emptyRemark()),
    pauseMarkup: () => set({ dropOn: null, activeLabel: null, editing: null,
      hoveredStroke: null, selected: { strokes: [], notes: [] }, lifted: false }),
    dropMarks: (strokes, noteIds, boxes) => set((state) => {
      const gone = new Set(strokes);
      const goneNotes = new Set(noteIds);
      // A ring, its leader and its label are one gesture, including chained links.
      let grew = true;
      while (grew) {
        grew = false;
        for (const note of state.notes) {
          const linked = [note.onStroke, note.ringStroke].filter((i): i is number => i !== undefined);
          if (!goneNotes.has(note.id) && !linked.some((i) => gone.has(i))) continue;
          if (!goneNotes.has(note.id)) { goneNotes.add(note.id); grew = true; }
          for (const i of linked) if (!gone.has(i)) { gone.add(i); grew = true; }
        }
      }
      const marks = state.marks.filter((_, i) => !gone.has(i));
      const reindex = (i: number | undefined) => i === undefined || gone.has(i)
        ? undefined : i - [...gone].filter((removed) => removed < i).length;
      return {
        marks,
        notes: state.notes.filter((note) => !goneNotes.has(note.id))
          .filter((note) => note.inStroke === undefined || !gone.has(note.inStroke))
          .map((note) => ({ ...note, inStroke: reindex(note.inStroke),
            onStroke: reindex(note.onStroke), ringStroke: reindex(note.ringStroke) })),
        ids: state.manual ?? markHits(marks.map((mark) => mark.points), boxes),
        selected: { strokes: [], notes: [] }, activeLabel: null, hoveredStroke: null,
      };
    }),
    recolour: (color) => set((state) => {
      const strokes = new Set(state.selected.strokes);
      const notes = new Set(state.selected.notes);
      return {
        ink: color,
        marks: state.marks.map((mark, i) => strokes.has(i) ? { ...mark, color } : mark),
        notes: state.notes.map((note) => notes.has(note.id) ||
          (note.inStroke !== undefined && strokes.has(note.inStroke)) ? { ...note, color } : note),
      };
    }),
    moveLabel: (id, to, boxes) => set((state) => {
      const note = state.notes.find((note) => note.id === id);
      if (!note) return {};
      const i = note.onStroke;
      if (i !== undefined && state.marks[i]) {
        const swung = pivotStroke(state.marks[i]!.points, to);
        const marks = state.marks.map((mark, k) => k === i ? { ...mark, points: swung } : mark);
        const { end, from } = strokeHeading(swung);
        return { marks, ids: state.manual ?? markHits(marks.map((mark) => mark.points), boxes),
          notes: state.notes.map((note) => note.id === id ? { ...note, x: end.x, y: end.y, from } : note) };
      }
      return { notes: state.notes.map((note) => note.id === id ? { ...note, x: to.x, y: to.y, pinned: true } : note) };
    }),
    newStack: (snapshot) => set((state) => {
      if (!hasRemark(state)) return {};
      const shelf = [...state.shelf, { ...snapshot, ground: state.ground }];
      const used = new Set([...state.shelf.flatMap((stack) => stack.marks.map((mark) => mark.color)),
        ...state.filed.flatMap((filed) => filed.marks.map((mark) => mark.color)), state.ink]);
      const at = PALETTE.findIndex((pen) => pen.ink === state.ink);
      const order = [...PALETTE.slice(at + 1), ...PALETTE.slice(0, at + 1)];
      const fresh = order.find((pen) => !used.has(pen.ink)) ?? order[0];
      const groundSeq = state.groundSeq + 1;
      return { ...emptyRemark(), shelf, groundSeq,
        ground: GHOST_GROUNDS[groundSeq % GHOST_GROUNDS.length] ?? GHOST_GROUNDS[0],
        ink: fresh?.ink ?? state.ink };
    }),
    switchStack: (id, snapshot) => set((state) => {
      const target = state.shelf.find((stack) => stack.id === id);
      if (!target) return {};
      const shelf = hasRemark(state) ? [...state.shelf, { ...snapshot, ground: state.ground }] : state.shelf;
      return { ...emptyRemark(), shelf: shelf.filter((stack) => stack.id !== id),
        marks: target.marks, notes: target.notes.map((note) => ({ ...note, offered: false })),
        ids: target.ids, manual: target.ids, ground: target.ground,
        ink: target.marks[target.marks.length - 1]?.color ?? state.ink };
    }),
    send: async (snapshot, create) => {
      if (get().sending) return false;
      const ground = get().ground;
      set({ sending: true });
      try {
        const created = await create();
        set((state) => {
          const groundSeq = state.groundSeq + 1;
          return { ...emptyRemark(), groundSeq,
            ground: GHOST_GROUNDS[groundSeq % GHOST_GROUNDS.length] ?? GHOST_GROUNDS[0],
            filed: [...state.filed, { intentId: created.id, text: snapshot.text, ids: snapshot.ids,
              sketch: snapshot.sketch, marks: snapshot.marks, notes: snapshot.notes,
              color: snapshot.marks[0]?.color ?? PALETTE[0].ink, ground, intent: created }] };
        });
        return true;
      } finally { set({ sending: false }); }
    },
    settle: async (intentId, judged, host) => {
      try {
        const intent = await host.get(intentId);
        if (!intent || intent.status !== "pending") return;
        const open = (intent.items ?? []).some((item) => item.type === "suggestion" &&
          (item.state === "pending" || (item.state === "applied" &&
            item.author.kind !== "human" && !judged.has(item.id))));
        if (!open) await host.resolve(intentId, { verdict: "judged on the board" });
      } catch { /* The next poll shows whatever state the server is in. */ }
    },
  }));
}
