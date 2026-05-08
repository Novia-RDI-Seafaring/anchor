import { Handle, Position, type NodeProps } from "@xyflow/react";

import { Compartment } from "./_shared/Compartment";

/**
 * SysmlBlockPrimitive — renders a SysML v2 block definition or block usage
 * (a "part") as a compartmented card. Mirrors UML block notation: title row
 * with a stereotype keyword, then optional ATTRIBUTES / PARTS / PORTS
 * compartments. Empty compartments are suppressed.
 *
 * Backend contract (anchor_sysml extension):
 *   data.kind            "block-def" | "block-usage"
 *   data.qualified_name  "Drone_SystemArchitecture::drone"
 *   data.short_name      "drone"
 *   data.attributes      [{ name, type?, default? }, ...]
 *   data.ports           [{ name, direction?: "in"|"out"|"inout", type? }, ...]
 *   data.parts           [{ name, type? }, ...]
 *   data.doc             optional doc-comment string
 *   data.source_ref      { kind: "sysml-text", file?, line?, col? }
 *
 * Visual differentiation:
 *   - block-def  → solid border  (the type definition)
 *   - block-usage → dashed border (an instance/part)
 *
 * Ports surface as ReactFlow Handles keyed `port-{name}`. Direction picks
 * the side (in → left, out → right, inout → both). This is what lets the
 * backend's `interface-connection` edges wire to specific ports via
 * `sourceHandle`/`targetHandle`.
 */

type Attribute = { name: string; type?: string | null; default?: string | null };
type Port = { name: string; direction?: "in" | "out" | "inout" | null; type?: string | null };
type Part = { name: string; type?: string | null };
type SourceRef = { kind?: string; file?: string | null; line?: number | null; col?: number | null };

type BlockData = {
  kind?: "block-def" | "block-usage";
  qualified_name?: string;
  short_name?: string;
  attributes?: Attribute[];
  ports?: Port[];
  parts?: Part[];
  doc?: string | null;
  metadata?: Record<string, string>;
  source_ref?: SourceRef;
  /** Allow the host to override the displayed label; falls back to short_name. */
  label?: string;
};

const STEREOTYPE: Record<string, string> = {
  "block-def": "«block def»",
  "block-usage": "«part»",
};

function formatType(type?: string | null): string {
  return type ? ` : ${type}` : "";
}

function formatDefault(value?: string | null): string {
  return value ? ` = ${value}` : "";
}

/**
 * Pick handle sides per port direction.
 *  in     → target handle on the LEFT
 *  out    → source handle on the RIGHT
 *  inout  → both
 *  null/undefined → both (safest default; the backend may omit direction)
 */
function portSides(dir?: Port["direction"]): { left: boolean; right: boolean } {
  if (dir === "in") return { left: true, right: false };
  if (dir === "out") return { left: false, right: true };
  return { left: true, right: true };
}

export function SysmlBlockPrimitive({ data }: NodeProps) {
  const d = (data ?? {}) as BlockData;
  const kind = d.kind ?? "block-def";
  const stereotype = STEREOTYPE[kind] ?? STEREOTYPE["block-def"];
  const shortName = d.short_name ?? d.label ?? "block";
  const qualified = d.qualified_name ?? shortName;
  const attributes = d.attributes ?? [];
  const ports = d.ports ?? [];
  const parts = d.parts ?? [];
  const borderStyle = kind === "block-usage" ? "border-dashed" : "border-solid";
  const sourceFile = d.source_ref?.file;

  // Header is always present; the first compartment after it gets a divider
  // automatically (it's not the first card section). Track this so the very
  // first body compartment doesn't double-up borders.
  let firstCompartment = true;
  const markFirst = () => {
    const v = firstCompartment;
    firstCompartment = false;
    return v;
  };

  return (
    <div
      className={`w-[280px] rounded-lg border-2 ${borderStyle} border-neutral-400 bg-white text-sm shadow-sm`}
      title={qualified}
    >
      {/* Header */}
      <div className="border-b border-neutral-200 px-3 py-2">
        <div className="text-[10px] uppercase tracking-wide text-neutral-500">
          {stereotype}
        </div>
        <div className="truncate font-medium text-neutral-900">{shortName}</div>
      </div>

      {/* Optional doc comment, italic */}
      {d.doc ? (
        <div className="border-b border-neutral-200 px-3 py-1.5 text-[11px] italic leading-snug text-neutral-600">
          {d.doc}
        </div>
      ) : null}

      {/* ATTRIBUTES */}
      {attributes.length > 0 ? (
        <Compartment label="attributes" first={markFirst()}>
          <ul className="space-y-0.5">
            {attributes.map((a, i) => (
              <li key={`a-${a.name}-${i}`} className="font-mono text-[11px] text-neutral-800">
                <span>{a.name}</span>
                <span className="text-neutral-500">{formatType(a.type)}</span>
                <span className="text-neutral-500">{formatDefault(a.default)}</span>
              </li>
            ))}
          </ul>
        </Compartment>
      ) : null}

      {/* PARTS */}
      {parts.length > 0 ? (
        <Compartment label="parts" first={markFirst()}>
          <ul className="space-y-0.5">
            {parts.map((p, i) => (
              <li key={`p-${p.name}-${i}`} className="font-mono text-[11px] text-neutral-800">
                <span>{p.name}</span>
                <span className="text-neutral-500">{formatType(p.type)}</span>
              </li>
            ))}
          </ul>
        </Compartment>
      ) : null}

      {/* PORTS — each port also surfaces as a ReactFlow Handle on the left/right edge */}
      {ports.length > 0 ? (
        <Compartment label="ports" first={markFirst()}>
          <ul className="space-y-0.5">
            {ports.map((p, i) => {
              const sides = portSides(p.direction);
              const arrow = p.direction === "in"
                ? "◀"
                : p.direction === "out"
                  ? "▶"
                  : "◆";
              return (
                <li
                  key={`port-${p.name}-${i}`}
                  className="relative font-mono text-[11px] text-neutral-800"
                >
                  <span className="text-neutral-500 mr-1">{arrow}</span>
                  <span>{p.name}</span>
                  <span className="text-neutral-500">{formatType(p.type)}</span>
                  {sides.left ? (
                    <Handle
                      id={`port-${p.name}`}
                      type="target"
                      position={Position.Left}
                      // Snap the handle to the row's vertical centre. Using
                      // `top: 50%` aligns the marker with the row text.
                      style={{ top: "50%", left: -6 }}
                    />
                  ) : null}
                  {sides.right ? (
                    <Handle
                      id={`port-${p.name}`}
                      type="source"
                      position={Position.Right}
                      style={{ top: "50%", right: -6 }}
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        </Compartment>
      ) : null}

      {/* Footer — source file link (text only; the canvas can intercept clicks
          via a future jump-to-source action). Kept compact so empty blocks
          stay short. */}
      {sourceFile ? (
        <div className="border-t border-neutral-200 px-3 py-1 text-[10px] text-neutral-500">
          <span className="font-mono">{sourceFile}</span>
          {d.source_ref?.line ? <span>:{d.source_ref.line}</span> : null}
        </div>
      ) : null}

      {/* Generic body-level handles for non-port edges (inheritance,
          composition, satisfy targets, etc.). Ports get their own keyed
          handles above; these unkeyed ones remain available for whole-block
          relationships. */}
      <Handle id="block-in" type="target" position={Position.Top} />
      <Handle id="block-out" type="source" position={Position.Bottom} />
    </div>
  );
}
