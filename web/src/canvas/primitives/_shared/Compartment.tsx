import type { ReactNode } from "react";

/**
 * Compartment — a labelled section inside a primitive card.
 *
 * Used by SysML primitives (and, in a follow-up, TablePrimitive) to render
 * the standard "header strip + body" pattern that splits a node into named
 * regions: attributes, ports, parts, asserts, etc.
 *
 * Visual contract: top border on every compartment except the first, a
 * small uppercase tracking-wide label, and a `px-3 py-1.5` body slot. Keep
 * this dumb — no state, no callbacks. Hosts compose rows themselves.
 */
type Props = {
  label: string;
  /** When true, suppress the top divider border (use for the first compartment in a card). */
  first?: boolean;
  /** Optional className appended to the body wrapper. */
  bodyClassName?: string;
  children: ReactNode;
};

export function Compartment({ label, first, bodyClassName, children }: Props) {
  const borderTop = first ? "" : "border-t border-neutral-200";
  return (
    <div className={borderTop}>
      <div className="px-3 pt-1.5 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className={`px-3 pb-1.5 ${bodyClassName ?? ""}`}>{children}</div>
    </div>
  );
}
