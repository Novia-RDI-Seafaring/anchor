import { describe, expect, it, vi } from "vitest";
import { createFormTransport } from "../../../examples/intent-layer/transport";
import { previewFields } from "../../../examples/intent-layer/formHost";
import type { DomTarget } from "../../../examples/intent-layer/metadata";
import type { Screenshot } from "../../../examples/intent-layer/capture";

const target: DomTarget = { id: "email", tag: "label", label: "Email", box: { id: "email", x: 10, y: 20, width: 200, height: 80 } };
const initial = { fields: { email: "old@example.test", max_flow: 42 }, revision: 0 };
const wire = { id: "ask", targets: ["email"], payload: { text: "Check" }, created_at: 1, status: "pending", items: [] };
function transportFixture() {
  const stateChanged = vi.fn();
  const request = vi.fn(async (path: RequestInfo | URL, _init?: RequestInit) => ({
    ok: true, json: async () => path === "/form/state" ? initial : ({ intents: [wire], intent: wire, item: { id: "s" } }),
  } as Response));
  const events = { addEventListener: vi.fn(), removeEventListener: vi.fn(), close: vi.fn() } as unknown as EventSource;
  const createEvents = vi.fn(() => events);
  return { stateChanged, request, events, createEvents };
}
describe("independent form thread transport", () => {
  it("keeps screenshot and DOM geometry in host payload and translates only the scoped wire envelope", async () => {
    const fixture = transportFixture();
    const screenshot = { mime: "image/png", dataUrl: "data:image/png;base64,FRAME", capture: "browser-tab" } as Screenshot;
    const transport = createFormTransport(fixture.stateChanged, () => ({ targets: [target], screenshot }), fixture.request, fixture.createEvents);
    expect((await transport.thread.loadScoped())[0]?.targetIds).toEqual(["email"]);
    expect(fixture.request).toHaveBeenCalledWith("/form/inbox?canvas=signup", undefined);
    await transport.thread.submit({ text: "Check", targetIds: ["email"] });
    const [, options] = fixture.request.mock.calls.at(-1)!;
    expect(JSON.parse(String(options?.body))).toEqual({
      kind: "user_request", origin_canvas_id: "signup", targets: ["email"],
      payload: { text: "Check", dom_targets: [target], screenshot },
    });
    const fallback = createFormTransport(fixture.stateChanged, () => ({ targets: [target] }), fixture.request, fixture.createEvents);
    await fallback.thread.submit({ text: "No screenshot", targetIds: ["email"] });
    expect(JSON.parse(String(fixture.request.mock.calls.at(-1)?.[1]?.body)).payload).not.toHaveProperty("screenshot");
  });
  it("runs apply/revert at the backend and refreshes real host state, then cleans the count subscription", async () => {
    const fixture = transportFixture();
    const transport = createFormTransport(fixture.stateChanged, () => ({ targets: [] }), fixture.request, fixture.createEvents);
    const changed = vi.fn(), release = transport.thread.subscribeChanged(changed);
    await transport.thread.apply("ask", "s");
    expect(fixture.request).toHaveBeenCalledWith("/form/inbox/ask/items/s/apply", expect.objectContaining({ body: "{}" }));
    expect(fixture.stateChanged).toHaveBeenCalledWith(initial);
    await transport.thread.revert("ask", "s");
    expect(fixture.request).toHaveBeenCalledWith("/form/inbox/ask/items/s/revert", expect.anything());
    expect(changed).toHaveBeenCalledTimes(2);
    release();
    expect(fixture.events.close).toHaveBeenCalledOnce();
    expect(fixture.events.removeEventListener).toHaveBeenCalledWith("intent_pending", expect.any(Function));
  });
  it("rejects backend errors without reporting a successful host change", async () => {
    const fixture = transportFixture();
    fixture.request.mockResolvedValueOnce({ ok: false, json: async () => ({ error: "apply_failed", message: "Invalid field" }) } as Response);
    const transport = createFormTransport(fixture.stateChanged, () => ({ targets: [] }), fixture.request, fixture.createEvents);
    await expect(transport.thread.apply("ask", "s")).rejects.toThrow("Invalid field");
    expect(fixture.stateChanged).not.toHaveBeenCalled();
  });
  it("previews typed field changes inertly and ignores unrelated or malformed operations", () => {
    const fields = { ...initial.fields };
    const preview = previewFields({ id: "s", type: "suggestion", author: { kind: "agent" }, text: "", state: "pending", created_at: 1,
      ops: [{ type: "FieldSet", payload: { field: "email", value: "work@example.test" } },
        { type: "eval", payload: { field: "email", value: "executable" } }] }, [target], fields);
    expect(preview?.nodes[0]).toMatchObject({ label: "Email", rows: [{ key: "Value", value: "work@example.test" }],
      before: { label: "Email", rows: [{ key: "Value", value: "old@example.test" }] } });
    expect(fields).toEqual(initial.fields);
  });
});
