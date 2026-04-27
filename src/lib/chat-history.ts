export type PersistableChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  type: "text";
};

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
  return messages.flatMap((message, index) => {
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
}

