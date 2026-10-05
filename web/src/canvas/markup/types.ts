import { type RowBand } from "@/canvas/cuts";
import {
  type Box,
  type CalloutPlace,
  type Point,
  type Rect
} from "@/canvas/lasso";
import { type Preview } from "@/canvas/preview";
import { type EdgePath } from "@/canvas/strikes";
import type { useCanvasStore } from "@/stores/canvasStore";
import type { createMarkupStore, Filed, Note, Selection, Stack } from "@/stores/markupStore";
import type { ThreadItem } from "@/api/intents";

type MarkupStoreValue = ReturnType<ReturnType<typeof createMarkupStore>["getState"]>;
type Ghost = {
  f: Filed;
  blob: Point[] | null;
  status: ThreadItem | undefined;
  questions: ThreadItem[];
  suggestion: ThreadItem | undefined;
  applied: ThreadItem | undefined;
  placed: ThreadItem[];
  items: ThreadItem[];
  preview: Preview | null;
};

export type MarkupProps = {
  active: boolean;
  /** Every node's box, in flow coordinates. */
  boxes: Box[];
  /** The canvas the remark is about. */
  workspaceSlug: string;
  /** Called once remarks have been filed. */
  onFiled?: () => void;
  /** Put the pen down: escape with nothing left to clear leaves the mode. */
  onExit?: () => void;
};

/** Internal composition state; host callers use MarkupProps. */
export type MarkupModel = {
  lifted: boolean;
  remarkBlob: Point[] | null;
  screen: (p: Point) => { x: number; y: number; };
  ground: string;
  ghosts: Ghost[];
  openFiled: string | null;
  viewport: import("@xyflow/react").Viewport;
  storeNodes: ReturnType<typeof useCanvasStore.getState>["nodes"];
  shelf: Stack[];
  blobOf: (st: Pick<Stack, "marks" | "notes" | "ids">) => Point[] | null;
  hoverShelf: string | null;
  notes: Note[];
  lineFrom: (n: Note) => Point | undefined;
  notePos: (n: Note) => Point;
  calledOut: Map<string, CalloutPlace>;
  dropOn: string | null;
  boxes: Box[];
  ink: string;
  ids: string[];
  marks: import("@/stores/markupStore").Mark[];
  paths: { x: number; y: number; }[][];
  selected: Selection;
  all: Point[][];
  hoveredStroke: number | null;
  surfaceRef: React.RefObject<HTMLDivElement | null>;
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: (e?: React.PointerEvent) => void;
  onClick: (e: React.PointerEvent) => void;
  onDoubleClick: (e: React.PointerEvent) => void;
  strokes: Point[][];
  setNotes: MarkupStoreValue["updateNotes"];
  editing: string | null;
  markupStore: ReturnType<typeof createMarkupStore>;
  setEditing: MarkupStoreValue["editNote"];
  growHost: (index: number, neededHeight: number) => void;
  setSelected: MarkupStoreValue["selectMarks"];
  setActiveLabel: MarkupStoreValue["selectLabel"];
  labelDrag: React.RefObject<{ id: string; start: Point; from: Point; } | null>;
  toFlow: (e: { clientX: number; clientY: number; }) => import("@xyflow/react").XYPosition;
  moveLabel: (id: string, to: Point) => void;
  activeLabel: string | null;
  removeLabel: (id: string) => void;
  onExit?: () => void;
  newStack: () => void;
  reveal: (st: Pick<Stack, "marks" | "notes" | "ids">) => void;
  switchTo: (id: string) => void;
  filed: Filed[];
  answering: { item: string; text: string; } | null;
  setAnswering: MarkupStoreValue["writeAnswer"];
  keepSuggestion: (id: string) => Set<string>;
  settle: (intentId: string, judged: Set<string>) => Promise<void>;
  kept: Set<string>;
  written: string;
  reading: import("@/canvas/sketch").Sketch;
  cutsReading: import("@/canvas/cuts").Cut[];
  reset: () => void;
  marquee: { a: Point; b: Point; } | null;
  lone: number | null;
  removeSelected: () => void;
  startGroupDrag: (mode: "move" | "resize", corner?: { x: 0 | 1; y: 0 | 1; }, over?: Selection) => (e: React.PointerEvent) => void;
  onGroupDragMove: (e: React.PointerEvent) => void;
  endGroupDrag: (e: React.PointerEvent) => void;
  picked: Rect | null;
  removeStroke: (index: number) => void;
  sayable: boolean;
  sending: boolean;
  sendRemark: () => Promise<void>;
  panelRef: React.RefObject<HTMLDivElement | null>;
  panelAt: Point | null;
  panelDrag: React.RefObject<{ startX: number; startY: number; x: number; y: number; } | null>;
  setPanelAt: MarkupStoreValue["movePanel"];
  current: Point[] | null;
  looping: boolean;
  strikesReading: import("@/canvas/strikes").Strike[];
  setOpenFiled: MarkupStoreValue["openThread"];
  active: boolean;
  workspaceSlug: string;
  applyMarks: MarkupStoreValue["replaceMarks"];
  setIds: MarkupStoreValue["setTargets"];
  manual: string[] | null;
  groupDrag: React.RefObject<{ mode: "move" | "resize"; from: Rect; start: Point; anchor: Point; strokes: (readonly [number, Point[]])[]; notes: (readonly [string, Point])[]; } | null>;
  getViewport: () => import("@xyflow/react").Viewport;
  drewJustNow: React.RefObject<boolean>;
  settledNotes: Note[];
  rowsOf: (nodeId: string) => RowBand[] | null;
  edgesOf: () => EdgePath[];
  setViewport: import("@xyflow/react").SetViewport;
  setCurrent: (update: React.SetStateAction<Point[] | null>) => void;
  setMarquee: (update: React.SetStateAction<{ a: Point; b: Point; } | null>) => void;
  onFiled?: () => void;
  panning: React.RefObject<{ x: number; y: number; vx: number; vy: number; } | null>;
  marqueeDrag: React.RefObject<boolean>;
  pullDrag: React.RefObject<{ index: number; grab: Point; start: Point; points: Point[]; reach: number; } | null>;
  drawing: React.RefObject<boolean>;
  setHoveredStroke: MarkupStoreValue["hoverMark"];
  shelfAt: (at: Point) => string | null;
  setHoverShelf: MarkupStoreValue["hoverStack"];
  setManual: MarkupStoreValue["setManualTargets"];
  setDropOn: MarkupStoreValue["previewJoin"];
  tapRef: React.RefObject<Point | null>;
  offScreen: () => Rect[];
  setMarginDeg: MarkupStoreValue["setMargin"];
  setLifted: MarkupStoreValue["liftPen"];
  storeEdges: ReturnType<typeof useCanvasStore.getState>["edges"];
  selectionRect: () => Rect | null;
};
