import { ModelOption } from "@/types";

export function normalizeModelOptions(rawModels: unknown): ModelOption[] {
  if (!Array.isArray(rawModels)) {
    return [];
  }

  const options: ModelOption[] = [];

  for (const entry of rawModels) {
    if (typeof entry === "string" && entry.trim()) {
      const id = entry.trim();
      options.push({
        id,
        label: id,
        provider: "Configured",
        type: /embed/i.test(id) ? "embedding" : "chat",
      });
      continue;
    }

    if (!entry || typeof entry !== "object") {
      continue;
    }

    const record = entry as Record<string, unknown>;
    const id =
      (typeof record.id === "string" && record.id) ||
      (typeof record.model_id === "string" && record.model_id) ||
      (typeof record.label === "string" && record.label);

    if (!id) {
      continue;
    }

    const label = typeof record.label === "string" && record.label ? record.label : id;
    const provider =
      typeof record.provider === "string" && record.provider ? record.provider : "Configured";
    const inferredType = /embed/i.test(id) || /embed/i.test(label) ? "embedding" : "chat";
    const type = record.type === "embedding" || record.type === "chat" ? record.type : inferredType;

    options.push({
      id,
      label,
      provider,
      type,
    });
  }

  return Array.from(new Map(options.map((option) => [option.id, option])).values());
}
