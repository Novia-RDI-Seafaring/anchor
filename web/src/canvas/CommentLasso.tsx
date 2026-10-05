import { useAnchorGeometry } from "./markup/AnchorGeometry";
import { useSelectionGestures } from "./markup/Gestures";
import { Ink } from "./markup/Ink";
import { ArchivedNotes, LiveNotes } from "./markup/NotesLayer";
import { deriveMarkupRender } from "./markup/renderModel";
import { Replies } from "./markup/Replies";
import { SelectionControls } from "./markup/SelectionControls";
import { Hotbar, Readout, SendRemark } from "./markup/Stacks";
import type { MarkupProps } from "./markup/types";
import { useInkGestures } from "./markup/useInkGestures";
import { useMarkupState } from "./markup/useMarkupState";
import { useNoteLayout } from "./markup/useNoteLayout";
import { usePenInput } from "./markup/usePenInput";
import { useStacks } from "./markup/useStacks";
import { useThreadReplies } from "./markup/useThreadReplies";

export function CommentLasso(props: MarkupProps) {
  const geometry = useAnchorGeometry();
  const state = useMarkupState(props);
  const base = { ...props, ...geometry, ...state };
  useThreadReplies(base);
  const layout = useNoteLayout(base);
  const withLayout = { ...base, ...layout };
  const selection = useSelectionGestures(withLayout);
  const withSelection = { ...withLayout, ...selection };
  const stacks = useStacks(withSelection);
  const withStacks = { ...withSelection, ...stacks };
  const ink = useInkGestures(withStacks);
  const controls = { ...withStacks, ...ink };
  usePenInput(controls);
  if (!props.active) return null;
  const model = { ...controls, ...deriveMarkupRender(controls) };
  const { lifted } = model;
  return (<div className="contents" data-pen-up={lifted ? "" : undefined}>
    <Ink model={model} />

    {/* The comments. No box, no border: a felt pen on the page rather than
          another card someone added. A note written inside a drawn shape takes
          that shape's size, so the box you drew is the thing you wrote in. */}
    <LiveNotes model={model} />

    {/* The pens, as a bar of slots along the bottom.

          A row of squares with the number on each, the one in hand raised and
          lit. Borrowed shamelessly from a game that solved this: the reader
          learns it at a glance, reaches for a key rather than a menu, and the
          bar says what 1 through 9 will do without being asked. */}
    <Hotbar model={model} />

    {/* Set-aside remarks' words, as ink. */}
    <ArchivedNotes model={model} />

    {/* The previewed cards, as they will read: label and rows. Laid over
          the real card for an update, so what the reader sees is the result;
          struck through for a removal. Approve is beside them, not beside a
          paragraph about them. */}
    <Replies model={model} />

    {/* The rubber band, while it is being dragged. */}
    <SelectionControls model={model} />

    {/* Queue it, under whatever the reader just wrote, so the confirmation
          is where their attention already is. */}
    <SendRemark model={model} />

    <Readout model={model} />
  </div>);
}
