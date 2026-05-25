/**
 * Optional in-app chat panel — speaks raw MCP via the backend's
 * `/mcp/sse` endpoint. Not enabled by default; flip
 * `VITE_ENABLE_CHAT=true` (or pass `enabled` prop) to render.
 *
 * The panel is intentionally minimal: a textarea, a send button, a
 * scroll area for assistant turns. It exists to *prove* that the
 * public MCP surface is enough — anything Claude Code or Cursor can do,
 * the in-app agent does the same way. Replace with whatever chat
 * library you prefer (CopilotKit, AG-UI, your own) by writing a
 * different component that hits the same MCP endpoint.
 */
import { useState } from "react";

import { BACKEND_URL } from "@/api/client";

type Message = { role: "user" | "assistant"; text: string };

export type ChatPanelProps = {
  enabled?: boolean;
  workspaceSlug: string;
};

export function ChatPanel({ enabled = false, workspaceSlug }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  if (!enabled && !import.meta.env.VITE_ENABLE_CHAT) return null;

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setBusy(true);
    try {
      // Placeholder: a real implementation would open an MCP session over
      // /mcp/sse and stream tool-calls + assistant text. Until that lands
      // we just echo so the wiring is testable.
      setMessages((prev) => [...prev, {
        role: "assistant",
        text: `(MCP wiring stub — sent to ${BACKEND_URL || "backend"} for canvas ${workspaceSlug})`,
      }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="flex h-full w-80 flex-col border-l border-neutral-200 bg-white">
      <header className="border-b border-neutral-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-neutral-700">
        Agent
      </header>
      <div className="flex-1 space-y-3 overflow-auto p-3 text-sm">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "ml-auto max-w-[85%] rounded bg-neutral-100 px-3 py-2"
                : "max-w-[85%] rounded bg-amber-50 px-3 py-2"
            }
          >
            {m.text}
          </div>
        ))}
      </div>
      <footer className="border-t border-neutral-200 p-2">
        <textarea
          className="w-full rounded border border-neutral-300 p-2 text-sm"
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Ask the agent…"
        />
      </footer>
    </aside>
  );
}
