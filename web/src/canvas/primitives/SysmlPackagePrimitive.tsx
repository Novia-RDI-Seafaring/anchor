import { type NodeProps } from "@xyflow/react";

/**
 * SysmlPackagePrimitive — container-style node for a SysML v2 package.
 *
 * A package is a namespace for blocks/requirements. On the canvas it's
 * rendered as a labelled, dashed rounded-rectangle that other nodes can
 * be parented inside via ReactFlow's `parentId` mechanism (the v2 store
 * preserves arbitrary `data` so the backend can drive parenting through
 * `data.parent` patches).
 *
 * Backend contract (anchor_sysml extension):
 *   data.qualified_name   "Drone_SystemArchitecture"
 *   data.short_name       "Drone_SystemArchitecture"
 *   data.doc              optional doc-comment string
 *   data.width / .height  layout dimensions (defaults: 600 x 400)
 *   data.source_ref       { kind: "sysml-text", file?, line?, col? }
 */

type SourceRef = { kind?: string; file?: string | null; line?: number | null; col?: number | null };

type PackageData = {
  qualified_name?: string;
  short_name?: string;
  doc?: string | null;
  width?: number;
  height?: number;
  metadata?: Record<string, string>;
  source_ref?: SourceRef;
  label?: string;
};

export function SysmlPackagePrimitive({ data }: NodeProps) {
  const d = (data ?? {}) as PackageData;
  const shortName = d.short_name ?? d.label ?? "package";
  const qualified = d.qualified_name ?? shortName;
  const w = d.width ?? 600;
  const h = d.height ?? 400;
  const sourceFile = d.source_ref?.file;

  return (
    <div
      // pointer-events-auto on the body so the label is selectable; children
      // parented inside still receive their own events.
      className="pointer-events-auto rounded-xl border-2 border-dashed border-neutral-500/70 bg-neutral-50/60"
      style={{ width: w, height: h }}
      title={qualified}
    >
      <div className="border-b border-neutral-300/70 bg-white/70 px-3 py-1.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-600">
            «package»
          </span>
          <span className="truncate text-[12px] font-medium text-neutral-800">
            {shortName}
          </span>
        </div>
        {d.doc ? (
          <div className="truncate text-[10px] italic text-neutral-500">{d.doc}</div>
        ) : null}
        {sourceFile ? (
          <div className="truncate text-[10px] font-mono text-neutral-400">
            {sourceFile}
            {d.source_ref?.line ? `:${d.source_ref.line}` : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
