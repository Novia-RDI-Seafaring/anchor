import { useEffect, useRef, useState } from "react";

export type TableCellFocus = {
  row: number;
  col: "key" | "value";
};

type Props = {
  rowIndex: number;
  col: "key" | "value";
  value: string;
  rowsLen: number;
  canEdit: boolean;
  marker?: boolean;
  pendingFocus: TableCellFocus | null;
  setPendingFocus: (next: TableCellFocus | null) => void;
  onCommit: (next: string) => void;
  onAppendRow: () => void;
};

/** Inline-editable key or value cell for a spec table row. */
export function TableRowCell({
  rowIndex,
  col,
  value,
  rowsLen,
  canEdit,
  marker = false,
  pendingFocus,
  setPendingFocus,
  onCommit,
  onAppendRow,
}: Props) {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (!pendingFocus) return;
    if (pendingFocus.row !== rowIndex || pendingFocus.col !== col) return;
    if (!canEdit) return;
    setDraft(value);
    setEditing(true);
    setPendingFocus(null);
  }, [pendingFocus, rowIndex, col, value, setPendingFocus, canEdit]);

  useEffect(() => {
    if (canEdit || !editing) return;
    setEditing(false);
    if (draft !== value) onCommit(draft);
  }, [canEdit, editing, draft, value, onCommit]);

  useEffect(() => {
    if (!editing) return;
    const input = inputRef.current;
    if (!input) return;
    input.focus();
    input.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };
  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };
  const isLastRow = rowIndex === rowsLen - 1;

  const handleKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      if (draft !== value) onCommit(draft);
      setEditing(false);
      if (event.shiftKey && isLastRow && col === "value") {
        onAppendRow();
      } else if (col === "key") {
        setPendingFocus({ row: rowIndex, col: "value" });
      } else if (!isLastRow) {
        setPendingFocus({ row: rowIndex + 1, col: "key" });
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      cancel();
      return;
    }
    event.stopPropagation();
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKey}
        onBlur={commit}
        onMouseDown={(event) => event.stopPropagation()}
        className="nodrag w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[12px] outline-none focus:border-neutral-500"
        placeholder={col === "key" ? "name" : "value"}
      />
    );
  }

  const markerClass = marker
    ? "nodrag inline-block max-w-full truncate align-bottom rounded-sm px-0.5 -mx-0.5 transition-colors duration-100 group-hover/tr:bg-yellow-200 group-hover/tr:text-neutral-900"
    : "nodrag block truncate";
  return (
    <span
      data-testid={marker ? "spec-value-marker" : undefined}
      className={`${markerClass} ${canEdit ? "cursor-text" : "cursor-pointer"}`}
      onDoubleClick={(event) => {
        if (!canEdit) return;
        event.stopPropagation();
        setDraft(value);
        setEditing(true);
      }}
      onClick={(event) => {
        if (!canEdit) return;
        event.stopPropagation();
        setDraft(value);
        setEditing(true);
      }}
      title={canEdit ? "click to edit" : undefined}
    >
      {value || <span className="italic text-neutral-300">{col === "key" ? "name" : "value"}</span>}
    </span>
  );
}
