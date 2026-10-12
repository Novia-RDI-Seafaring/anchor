import { useState } from "react";


/**
 * One line to say something back, under a card that asked for a verdict.
 *
 * Keep and put it back are the verdict; this is the rest of the sentence:
 * "put it back, I meant every other row". Without it the reader had to go
 * to the panel, find the thread, and write there -- a detour that mostly
 * ended in not saying it. Enter sends; the line clears and stays.
 */
export function ReplyLine({ color, onSend }: { color: string; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const send = () => {
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText("");
  };
  return (
    <div className="mt-1.5 flex gap-1">
      <input
        data-testid="comment-lasso-reply"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") send();
        }}
        placeholder={"reply\u2026"}
        className="min-w-0 flex-1 rounded border border-neutral-300 px-1.5 py-0.5 text-[11px] outline-none focus:border-neutral-500"
      />
      <button
        type="button"
        className="rounded px-2 py-0.5 text-[11px] text-white"
        style={{ background: color }}
        onClick={send}
      >
        send
      </button>
    </div>
  );
}
