import type { ThreadItem } from "./ports";

export function SuggestionMeta({ item, stale = false }: { item: ThreadItem; stale?: boolean }) {
  const count = item.ops?.length ?? 0;
  return <span className="text-[10px] text-neutral-500">
    <span>{count} operation{count === 1 ? "" : "s"}{item.state ? ` \u00b7 ${item.state}` : ""}</span>
    {stale && item.state === "pending" ? <>
      {" \u00b7 "}
      <span className="font-medium text-rose-700" title="An operation targets an item that is no longer on the canvas. The preview may be incomplete.">stale</span>
    </> : null}
  </span>;
}
