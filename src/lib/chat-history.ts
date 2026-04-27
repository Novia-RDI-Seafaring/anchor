export type PersistableChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  type: "text";
};

export function collapseAssistantRepliesByTurn<T extends { role: string }>(
  messages: T[],
  mergeAssistant?: (previous: T, current: T) => T,
): T[] {
  return messages.reduce<T[]>((collapsed, message) => {
    const lastIndex = collapsed.length - 1;
    const previous = collapsed[lastIndex];
    if (message.role === "assistant" && previous?.role === "assistant") {
      collapsed[lastIndex] = mergeAssistant ? mergeAssistant(previous, message) : message;
    } else {
      collapsed.push(message);
    }
    return collapsed;
  }, []);
}

function normalizeMessageContent(content: unknown): string {
  if (typeof content === "string") return content.trim();
  if (!Array.isArray(content)) return "";

  return content
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && (part as any).type === "text") {
        return String((part as any).text ?? "");
      }
      return "";
    })
    .join(" ")
    .trim();
}

export function toPersistableChatMessages(messages: any[] = []): PersistableChatMessage[] {
  const normalized = messages.flatMap((message, index) => {
    const role = message?.role;
    if (role !== "user" && role !== "assistant") return [];

    const content = normalizeMessageContent(message?.content);
    if (!content) return [];

    return [{
      id: String(message?.id ?? `${role}-${index}`),
      role,
      content,
      type: "text" as const,
    }];
  });

  return collapseAssistantRepliesByTurn(normalized);
}
