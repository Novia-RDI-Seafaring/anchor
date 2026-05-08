import { Handle, Position, type NodeProps } from "@xyflow/react";

import { Compartment } from "./_shared/Compartment";

/**
 * SysmlRequirementPrimitive — renders a SysML v2 requirement definition.
 *
 * Backend contract (anchor_sysml extension):
 *   data.qualified_name   "Drone_Requirements::battery_life"
 *   data.short_name       "battery_life"
 *   data.req_id           "REQ-9942" (optional)
 *   data.subject          name of the block this requirement is about
 *   data.asserts          [string, ...]   plain-text predicates
 *   data.doc              optional doc-comment string
 *   data.source_ref       { kind: "sysml-text", file?, line?, col? }
 *
 * Visual: solid border, `«requirement»` stereotype, optional req_id chip,
 * subject row, then the asserts list rendered in mono.
 */

type SourceRef = { kind?: string; file?: string | null; line?: number | null; col?: number | null };

type RequirementData = {
  qualified_name?: string;
  short_name?: string;
  req_id?: string | null;
  subject?: string | null;
  asserts?: string[];
  doc?: string | null;
  metadata?: Record<string, string>;
  source_ref?: SourceRef;
  label?: string;
};

export function SysmlRequirementPrimitive({ data }: NodeProps) {
  const d = (data ?? {}) as RequirementData;
  const shortName = d.short_name ?? d.label ?? "requirement";
  const qualified = d.qualified_name ?? shortName;
  const reqId = d.req_id;
  const subject = d.subject;
  const asserts = d.asserts ?? [];
  const sourceFile = d.source_ref?.file;

  let firstCompartment = true;
  const markFirst = () => {
    const v = firstCompartment;
    firstCompartment = false;
    return v;
  };

  return (
    <div
      className="w-[280px] rounded-lg border-2 border-solid border-neutral-400 bg-white text-sm shadow-sm"
      title={qualified}
    >
      {/* Header */}
      <div className="border-b border-neutral-200 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wide text-neutral-500">
              «requirement»
            </div>
            <div className="truncate font-medium text-neutral-900">{shortName}</div>
          </div>
          {reqId ? (
            <span
              className="shrink-0 rounded border border-sky-300 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700"
              title={`identifier: ${reqId}`}
            >
              {reqId}
            </span>
          ) : null}
        </div>
      </div>

      {/* Optional doc comment */}
      {d.doc ? (
        <div className="border-b border-neutral-200 px-3 py-1.5 text-[11px] italic leading-snug text-neutral-600">
          {d.doc}
        </div>
      ) : null}

      {/* SUBJECT */}
      {subject ? (
        <Compartment label="subject" first={markFirst()}>
          <div className="font-mono text-[11px] text-neutral-800">{subject}</div>
        </Compartment>
      ) : null}

      {/* ASSERTS — code-block style */}
      {asserts.length > 0 ? (
        <Compartment label="asserts" first={markFirst()}>
          <ul className="space-y-1">
            {asserts.map((stmt, i) => (
              <li
                key={`assert-${i}`}
                className="rounded bg-neutral-50 px-2 py-1 font-mono text-[11px] leading-snug text-neutral-800"
              >
                {stmt}
              </li>
            ))}
          </ul>
        </Compartment>
      ) : null}

      {/* Footer — source file link */}
      {sourceFile ? (
        <div className="border-t border-neutral-200 px-3 py-1 text-[10px] text-neutral-500">
          <span className="font-mono">{sourceFile}</span>
          {d.source_ref?.line ? <span>:{d.source_ref.line}</span> : null}
        </div>
      ) : null}

      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
