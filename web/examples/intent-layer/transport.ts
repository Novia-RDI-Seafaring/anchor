import type { Intent, OverlayHost, Submission, ThreadItem } from "../../src/intent-overlay";
import type { Screenshot } from "./capture";
import type { DomTarget } from "./metadata";

export type FormState = { fields: { email: string; max_flow: number }; revision: number };
type WireIntent = Intent & { targets?: unknown[] };
export type Evidence = { screenshot?: Screenshot; targets: DomTarget[] };

export function createFormTransport(
  stateChanged: (state: FormState) => void,
  evidence: () => Evidence,
  request: typeof fetch = fetch,
  createEvents: (url: string) => EventSource = (url) => new EventSource(url),
) {
  const listeners = new Set<() => void>();
  let events: EventSource | undefined;
  const notify = () => { for (const listener of listeners) listener(); };
  const root = "/form/inbox";
  async function json<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
    const response = await request(path, body === undefined ? undefined : {
      method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.message ?? result.error ?? "The form request failed.");
    return result as T;
  }
  const adapt = (wire: WireIntent): Intent => ({ ...wire,
    targetIds: (wire.targets ?? []).filter((target): target is string => typeof target === "string") });
  const state = async () => {
    const value = await json<FormState>("/form/state");
    stateChanged(value);
    return value;
  };
  async function mutate(id: string, itemId: string, action: string, body = {}): Promise<ThreadItem> {
    const value = await json<{ item: ThreadItem }>(root + "/" + encodeURIComponent(id) + "/items/" + encodeURIComponent(itemId) + "/" + action, body);
    if (action === "apply" || action === "revert") await state();
    notify();
    return value.item;
  }
  const thread: OverlayHost["thread"] = {
    loadScoped: async () => (await json<{ intents: WireIntent[] }>(root + "?canvas=signup")).intents.map(adapt),
    get: async (id) => {
      const value = await json<{ intent?: WireIntent }>(root + "/" + encodeURIComponent(id));
      return value.intent ? adapt(value.intent) : null;
    },
    submit: async ({ targetIds, ...remark }: Submission) => {
      const attached = evidence();
      const { intent } = await json<{ intent: WireIntent }>(root, {
        kind: "user_request", origin_canvas_id: "signup", targets: targetIds,
        payload: { ...remark, dom_targets: attached.targets.filter((target) => targetIds.includes(target.id)),
          ...(attached.screenshot ? { screenshot: attached.screenshot } : {}) },
      });
      notify();
      return adapt(intent);
    },
    addItem: async (id, body) => {
      const value = await json<{ item: ThreadItem }>(root + "/" + encodeURIComponent(id) + "/items", body);
      notify(); return value.item;
    },
    answer: (id, itemId, text) => mutate(id, itemId, "answer", { text }),
    apply: (id, itemId) => mutate(id, itemId, "apply"),
    revert: (id, itemId) => mutate(id, itemId, "revert"),
    decline: (id, itemId, comment) => mutate(id, itemId, "decline", comment ? { comment } : {}),
    resolve: async (id, result) => { const value = await json(root + "/" + encodeURIComponent(id) + "/resolve", { result }); notify(); return value; },
    subscribeChanged: (listener) => {
      listeners.add(listener);
      if (!events) { events = createEvents(root + "/events"); events.addEventListener("intent_pending", notify); }
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) { events?.removeEventListener("intent_pending", notify); events?.close(); events = undefined; }
      };
    },
  };
  return { thread, state,
    demoReply: async () => {
      const pending = await thread.loadScoped();
      if (!pending.length) throw new Error("Send a remark about a field first.");
      for (const intent of pending) await json("/form/demo-reply/" + encodeURIComponent(intent.id), {});
      notify();
    },
  };
}
