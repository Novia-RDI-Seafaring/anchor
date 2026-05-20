/**
 * LeftRail — sidebar with stacked tools.
 *
 * Two collapsible sections today: Palette (shape primitives) and Library
 * (browse OIP artefacts). Both write to the canvas through the same HTTP
 * API any external agent uses; the rail itself never touches canvas state.
 *
 * The rail can collapse to a ~40px icon strip (chevron button in the
 * header, or `[` keyboard shortcut). Collapsed mode keeps the category
 * icons clickable — pressing one auto-expands the rail to that tab so the
 * sidebar can still serve as a launcher without devouring screen real
 * estate. Preference is persisted in `uiStore.leftRailCollapsed`.
 */
import { ChevronLeft, ChevronRight, Library as LibraryIcon, Shapes } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useUiStore } from "@/stores/uiStore";

import { Library } from "./Library";
import { Palette } from "./Palette";

type Tab = "palette" | "library";

export function LeftRail({ workspaceSlug }: { workspaceSlug: string }) {
  const [tab, setTab] = useState<Tab>("palette");
  const collapsed = useUiStore((s) => s.leftRailCollapsed);
  const toggle = useUiStore((s) => s.toggleLeftRail);
  const setCollapsed = useUiStore((s) => s.setLeftRailCollapsed);

  // `[` toggles the rail. Ignore when typing in inputs/contenteditable so
  // we don't fight the user mid-rename.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "[") return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={`flex h-full shrink-0 flex-col border-r border-neutral-200 bg-neutral-50/60 transition-[width] duration-200 ease-out ${
          collapsed ? "w-10" : "w-60"
        }`}
        aria-label="Canvas tools"
      >
        <div
          className={`flex items-center border-b border-neutral-200 bg-white text-xs ${
            collapsed ? "flex-col gap-1 py-1" : ""
          }`}
        >
          {collapsed ? (
            <>
              <RailIconButton
                label="Palette"
                shortcut="palette · click to expand"
                active={tab === "palette"}
                onClick={() => {
                  setTab("palette");
                  setCollapsed(false);
                }}
              >
                <Shapes className="size-4" />
              </RailIconButton>
              <RailIconButton
                label="Library"
                shortcut="library · click to expand"
                active={tab === "library"}
                onClick={() => {
                  setTab("library");
                  setCollapsed(false);
                }}
              >
                <LibraryIcon className="size-4" />
              </RailIconButton>
              <div className="my-1 h-px w-6 bg-neutral-200" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={toggle}
                    aria-label="Expand left rail"
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  expand rail · <kbd className="font-mono">[</kbd>
                </TooltipContent>
              </Tooltip>
            </>
          ) : (
            <>
              <TabButton active={tab === "palette"} onClick={() => setTab("palette")}>
                Palette
              </TabButton>
              <TabButton active={tab === "library"} onClick={() => setTab("library")}>
                Library
              </TabButton>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={toggle}
                    aria-label="Collapse left rail"
                    className="mr-1"
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  collapse rail · <kbd className="font-mono">[</kbd>
                </TooltipContent>
              </Tooltip>
            </>
          )}
        </div>
        {collapsed ? null : (
          <div className="flex-1 overflow-y-auto p-2">
            {tab === "palette" ? <Palette workspaceSlug={workspaceSlug} /> : null}
            {tab === "library" ? <Library workspaceSlug={workspaceSlug} /> : null}
          </div>
        )}
      </aside>
    </TooltipProvider>
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

function RailIconButton({
  label,
  shortcut,
  active,
  onClick,
  children,
}: {
  label: string;
  shortcut: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onClick}
          aria-label={label}
          className={active ? "bg-neutral-200 text-neutral-900" : ""}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="right">{shortcut}</TooltipContent>
    </Tooltip>
  );
}
