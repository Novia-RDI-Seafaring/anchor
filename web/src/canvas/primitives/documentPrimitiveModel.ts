import { sameBbox } from "@/lib/bbox";

export const DOCUMENT_STATUS_STYLES: Record<string, string> = {
  pending: "border-amber-400 bg-amber-50",
  awaiting_agent: "border-amber-400 bg-amber-50",
  ingesting: "border-blue-400 bg-blue-50",
  searching: "border-blue-400 bg-blue-50",
  found: "border-emerald-400 bg-emerald-50",
  failed: "border-red-400 bg-red-50",
  ready: "border-neutral-300 bg-white",
};

export const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  pending: "queued",
  awaiting_agent: "awaiting agent",
  ingesting: "ingesting",
  searching: "ingesting",
  found: "ready",
  failed: "failed",
  ready: "ready",
};

export const DOCUMENT_RENDER_DPI = 150;
export const POINTS_PER_INCH = 72;

export type RegionHighlight = { regionId?: string; bbox?: number[] };

export function formatElapsed(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0s";
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  if (minutes <= 0) return `${secs}s`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours <= 0) return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
  return `${hours}h ${mins.toString().padStart(2, "0")}m`;
}

export function numericSeconds(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function matchesExternalHighlight(
  highlight: RegionHighlight | null,
  regionId: string,
  bbox: number[],
): boolean {
  if (!highlight) return false;
  if (highlight.bbox && !sameBbox(highlight.bbox, bbox)) return false;
  if (highlight.regionId) return highlight.regionId === regionId;
  return sameBbox(highlight.bbox, bbox);
}
