/** A source link is not a verdict. Bindings are issued by the server. */
export type EvidenceCheck = {
  status: "verified" | "unverified";
  code: string;
  message: string;
  next_step: string;
  claim: { key?: unknown; value?: unknown };
  source_ref?: unknown;
};

export type EvidenceRow = {
  key?: unknown;
  value?: unknown;
  source_ref?: unknown;
  evidence?: {
    status?: string;
    claim?: { key?: unknown; value?: unknown };
    source_ref?: unknown;
    validation?: unknown;
    check?: EvidenceCheck;
  };
};

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((k) => `${JSON.stringify(k)}:${canonical(record[k])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

const normalize = (value: unknown) => typeof value === "string" ? value.trim().replace(/\s+/g, " ") : value;

/** A completed check describes only the exact claim and source it checked. */
export function currentEvidenceCheck(row: EvidenceRow): EvidenceCheck | null {
  const check = row.evidence?.check;
  const key = normalize(row.key);
  if (!check || typeof check.message !== "string" || typeof check.next_step !== "string"
    || check.claim?.key !== (typeof key === "string" ? key.toLowerCase() : key)
    || check.claim?.value !== normalize(row.value)
    || canonical(check.source_ref ?? null) !== canonical(row.source_ref ?? null)
    || check.status === "verified" && evidenceState(row) !== "verified") return null;
  return check;
}

export function evidenceState(row: EvidenceRow): "verified" | "stale" | "unverified" | "none" {
  if (!row.source_ref) return "none";
  const evidence = row.evidence;
  if (evidence?.status === "stale") return "stale";
  if (evidence?.status !== "verified" || !evidence.claim || !evidence.validation) return "unverified";
  const key = normalize(row.key);
  const matches = evidence.claim.key === (typeof key === "string" ? key.toLowerCase() : key)
    && evidence.claim.value === normalize(row.value)
    && canonical(evidence.source_ref) === canonical(row.source_ref);
  // Also protects the optimistic local edit before the authoritative SSE echo.
  return matches ? "verified" : "stale";
}

export const evidenceLabels = {
  verified: "Verified", stale: "Stale", unverified: "Unverified", none: "No evidence",
};
