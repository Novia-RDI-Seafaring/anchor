export const EVIDENCE_EDGE_STROKE = "#059669";
export const EVIDENCE_EDGE_ACTIVE_STROKE = "#10b981";

/**
 * Resting (quiet) vs active stroke widths for evidence/provenance edges.
 *
 * Evidence edges render thin and low-contrast by default so a dense bundle
 * (N facts -> one source doc, the #183 "yarn ball") is not visually
 * overwhelming. On node hover the provenance path to the source thickens to
 * the active width and the rest stays quiet (and is further faded via the
 * edge's `dimmed` flag / opacity). Tuning the bundle's resting weight here
 * keeps both edge renderers (Floating + Anchored) in lock-step.
 */
export const EVIDENCE_EDGE_QUIET_WIDTH = 1.25;
export const EVIDENCE_EDGE_ACTIVE_WIDTH = 3;
/** Opacity applied to a quiet evidence edge so the resting bundle recedes. */
export const EVIDENCE_EDGE_QUIET_OPACITY = 0.55;

type EdgeVisualData = {
  kind?: string | null;
  active?: boolean;
  dimmed?: boolean;
} & Record<string, unknown>;

/**
 * Resolve the resting/active geometry for an evidence edge in one place so
 * the two renderers agree. Active edges (the hovered node's provenance path,
 * or a selected edge) thicken and run at full opacity; quiet edges are thin
 * and slightly translucent so the bundle stays calm.
 */
export function evidenceStrokeWidth(active: boolean): number {
  return active ? EVIDENCE_EDGE_ACTIVE_WIDTH : EVIDENCE_EDGE_QUIET_WIDTH;
}

/** True when CanvasGraph marked this edge as off-path (faded) on hover. */
export function isDimmedEvidence(data: unknown): boolean {
  return isEvidenceEdge(data) && (data as EdgeVisualData).dimmed === true;
}

type EndpointSocketProps = {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  stroke: string;
  evidence: boolean;
  active: boolean;
};

export function isEvidenceEdge(data: unknown): data is EdgeVisualData {
  return !!data && typeof data === "object" && (data as EdgeVisualData).kind === "evidence";
}

export function isActiveEvidence(data: unknown): boolean {
  return isEvidenceEdge(data) && (data as EdgeVisualData).active === true;
}

export function evidenceStroke(data: unknown): string {
  return isActiveEvidence(data) ? EVIDENCE_EDGE_ACTIVE_STROKE : EVIDENCE_EDGE_STROKE;
}

export function EvidencePathUnderlay({
  path,
  evidence,
}: {
  path: string;
  evidence: boolean;
}) {
  if (!evidence) return null;
  return (
    <path
      d={path}
      fill="none"
      stroke="#ffffff"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={5}
      opacity={0.9}
      pointerEvents="none"
    />
  );
}

export function EdgeEndpointSockets({
  sourceX,
  sourceY,
  targetX,
  targetY,
  stroke,
  evidence,
  active,
}: EndpointSocketProps) {
  if (!evidence) return null;
  const r = active ? 4.5 : 3.5;
  return (
    <g pointerEvents="none">
      <circle cx={sourceX} cy={sourceY} r={r + 2} fill="#ffffff" opacity={0.95} />
      <circle cx={targetX} cy={targetY} r={r + 2} fill="#ffffff" opacity={0.95} />
      <circle cx={sourceX} cy={sourceY} r={r} fill="#ffffff" stroke={stroke} strokeWidth={2} />
      <circle cx={targetX} cy={targetY} r={r} fill="#ffffff" stroke={stroke} strokeWidth={2} />
    </g>
  );
}
