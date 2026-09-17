import { api } from "./client";

/**
 * Proposal sets — reviewing what an agent added in one go, as one thing
 * (#359 backend, this module is the web half).
 *
 * Per-element review (#324) works for a stray node and falls apart for a
 * batch: thirty-five nodes built from one document are thirty-five verdicts,
 * with nothing recording which of them belong together or why. A proposal set
 * is one record naming its members plus the reason they were added, so a human
 * gives one verdict for the whole batch.
 *
 * Wraps the same HTTP endpoints the MCP / CLI adapters mirror:
 *   - `GET  /api/workspaces/{slug}/proposal-sets`              -> every set
 *   - `GET  /api/workspaces/{slug}/proposal-sets/{id}`         -> one set
 *   - `POST /api/workspaces/{slug}/proposal-sets`              -> open one
 *   - `POST /api/workspaces/{slug}/proposal-sets/{id}/members` -> add members
 *   - `POST /api/workspaces/{slug}/proposal-sets/{id}/review`  -> one verdict
 *
 * Membership is NOT stamped on the elements: the set record names them. That
 * is why the UI has to hold the list in a store to mark a member node, rather
 * than reading it off `node.data`.
 */

/** Who opened or reviewed a set. Mirrors the server's `actor_ref` shape. */
export type ProposalActor = {
  kind: "agent" | "human" | "system" | (string & {});
  label?: string;
};

/** One element in a set. A set can group both nodes and edges. */
export type ProposalMember = {
  kind: "node" | "edge";
  id: string;
};

/** Lifecycle of a set. `open` means it is still waiting for a human verdict. */
export type ProposalSetState = "open" | "accepted" | "rejected";

/** Mirrors one record in `Workspace.metadata['proposal_sets']`. */
export type ProposalSet = {
  id: string;
  reason: string;
  by: ProposalActor;
  /** Unix seconds when the set was opened. */
  at: number;
  members: ProposalMember[];
  state: ProposalSetState;
  reviewed_by?: ProposalActor;
  /** Unix seconds when the verdict landed. */
  reviewed_at?: number;
  /** True when a rejection removed the members instead of stamping them. */
  discarded?: boolean;
};

/** A verdict a human can give. `open` is not a verdict, so it is excluded. */
export type ProposalVerdict = Extract<ProposalSetState, "accepted" | "rejected">;

/** What a review returns: the stored record plus how many elements it touched. */
export type ProposalReviewResult = {
  proposal_set: ProposalSet;
  events: number;
};

/**
 * Browser event dispatched after any proposal-set mutate in this window.
 * A UI-only nudge, the same pattern as `anchor:references-changed`, so the
 * panel refetches immediately instead of waiting for the canvas SSE to land.
 * `detail.slug` is the canvas the mutation hit so a listener can ignore other
 * canvases.
 */
export const PROPOSAL_SETS_CHANGED_EVENT = "anchor:proposal-sets-changed";

export function emitProposalSetsChanged(slug: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(PROPOSAL_SETS_CHANGED_EVENT, { detail: { slug } }),
  );
}

/**
 * Pull the authored message out of a failed request.
 *
 * `api` throws with the whole response body appended to the message, and
 * FastAPI puts the human-readable part in `{"detail": "..."}`. Rendering the
 * raw JSON into the panel reads like a crash rather than an answer, so unwrap
 * it. Anything that is not a JSON body falls through unchanged.
 */
export function errorDetail(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  const brace = raw.indexOf("{");
  if (brace >= 0) {
    try {
      const body = JSON.parse(raw.slice(brace)) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) return body.detail;
    } catch {
      // Not a JSON body after all. Keep the raw message.
    }
  }
  return raw;
}

async function unwrap<T>(call: Promise<T>): Promise<T> {
  try {
    return await call;
  } catch (err) {
    throw new Error(errorDetail(err));
  }
}

export const proposalSets = {
  /** Every set on the canvas, oldest first. `state` narrows the list. */
  list: async (
    canvasSlug: string,
    options?: { state?: ProposalSetState },
  ): Promise<ProposalSet[]> => {
    const query = options?.state
      ? `?state=${encodeURIComponent(options.state)}`
      : "";
    const res = await unwrap(
      api.get<{ proposal_sets: ProposalSet[] }>(
        `/api/workspaces/${canvasSlug}/proposal-sets${query}`,
      ),
    );
    return res.proposal_sets ?? [];
  },

  get: (canvasSlug: string, setId: string): Promise<ProposalSet> =>
    unwrap(
      api.get<ProposalSet>(
        `/api/workspaces/${canvasSlug}/proposal-sets/${setId}`,
      ),
    ),

  /**
   * Group elements into one reviewable set. `members` may be left out and
   * filled in later with `addMembers` — an agent that opens the set first can
   * add each element as it creates it.
   */
  open: async (
    canvasSlug: string,
    body: { reason: string; members?: ProposalMember[] },
  ): Promise<ProposalSet> => {
    const created = await unwrap(
      api.post<ProposalSet>(`/api/workspaces/${canvasSlug}/proposal-sets`, {
        reason: body.reason,
        members: body.members ?? [],
      }),
    );
    emitProposalSetsChanged(canvasSlug);
    return created;
  },

  /** Add elements to an open set. Re-adding a member is a no-op server-side. */
  addMembers: async (
    canvasSlug: string,
    setId: string,
    members: ProposalMember[],
  ): Promise<ProposalSet> => {
    const updated = await unwrap(
      api.post<ProposalSet>(
        `/api/workspaces/${canvasSlug}/proposal-sets/${setId}/members`,
        { members },
      ),
    );
    emitProposalSetsChanged(canvasSlug);
    return updated;
  },

  /**
   * Accept or reject a whole set in one write.
   *
   * Accepting stamps `data.review.state = "accepted"` on every member;
   * rejecting stamps `"rejected"`, which stays on the element as feedback the
   * agent can read. `discard` (rejections only) removes the members instead,
   * cascading their edges, so it is destructive and the UI confirms it first.
   * `exceptIds` leaves those members untouched.
   */
  review: async (
    canvasSlug: string,
    setId: string,
    body: {
      verdict: ProposalVerdict;
      discard?: boolean;
      exceptIds?: string[];
    },
  ): Promise<ProposalReviewResult> => {
    const res = await unwrap(
      api.post<ProposalReviewResult>(
        `/api/workspaces/${canvasSlug}/proposal-sets/${setId}/review`,
        {
          verdict: body.verdict,
          discard: body.discard ?? false,
          ...(body.exceptIds ? { except_ids: body.exceptIds } : {}),
        },
      ),
    );
    emitProposalSetsChanged(canvasSlug);
    return res;
  },
};
