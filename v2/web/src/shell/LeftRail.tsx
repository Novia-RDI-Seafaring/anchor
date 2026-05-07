/**
 * LeftRail — sidebar with stacked tools.
 *
 * Two collapsible sections today: Palette (shape primitives) and Library
 * (browse OIP artefacts). Both write to the canvas through the same HTTP
 * API any external agent uses; the rail itself never touches canvas state.
 */
import { useState } from "react";

import { Library } from "./Library";
import { Palette } from "./Palette";

type Tab = "palette" | "library";

export function LeftRail({ workspaceSlug }: { workspaceSlug: string }) {
  const [tab, setTab] = useState<Tab>("palette");

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-neutral-200 bg-neutral-50/60">
      <div className="flex border-b border-neutral-200 bg-white text-xs">
        <TabButton active={tab === "palette"} onClick={() => setTab("palette")}>
          Palette
        </TabButton>
        <TabButton active={tab === "library"} onClick={() => setTab("library")}>
          Library
        </TabButton>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {tab === "palette" ? <Palette workspaceSlug={workspaceSlug} /> : null}
        {tab === "library" ? <Library workspaceSlug={workspaceSlug} /> : null}
      </div>
    </aside>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-3 py-2 text-center transition ${
        active
          ? "border-b-2 border-neutral-900 font-semibold text-neutral-900"
          : "text-neutral-500 hover:text-neutral-700"
      }`}
    >
      {children}
    </button>
  );
}
