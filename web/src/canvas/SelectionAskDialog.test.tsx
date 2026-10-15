import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { SelectionAskDialog } from "./SelectionAskDialog";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("asking about an existing selection", () => {
  it("offers no composer or request for an empty selection", () => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request);
    render(<SelectionAskDialog workspaceSlug="study" targetIds={[]} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });

  it.each([["pump"], ["pump", "limits", "drawing"]])("queues exactly the supplied targets %j without editing nodes", async (...targetIds) => {
    const selected = { selectedNodeId: "pump", armedTool: null, navigationMode: "select" as const };
    useUiStore.setState(selected);
    const nodes = { pump: { id: "pump", node_type: "concept", label: "Pump", x: 10, y: 20, data: {} } };
    useCanvasStore.setState({ nodes, version: 7 });
    const request = vi.fn(async () => new Response(JSON.stringify({ intent: { id: "ask-1", targets: targetIds } }), { status: 200 }));
    vi.stubGlobal("fetch", request);
    const patch = vi.spyOn(canvases, "patchNode");
    const before = JSON.stringify(useCanvasStore.getState().nodes);
    render(<SelectionAskDialog workspaceSlug="study" targetIds={targetIds} onClose={vi.fn()} />);
    const text = screen.getByRole("textbox", { name: "Your request" });
    expect(document.activeElement).toBe(text);
    expect(screen.getByRole("button", { name: "Send to agent" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(text, { target: { value: "  Compare the operating limits  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send to agent" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Request queued"));
    expect(request).toHaveBeenCalledOnce();
    const [url, init] = request.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/intents");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      kind: "user_request", origin_canvas_id: "study", payload: { text: "Compare the operating limits" },
      targets: targetIds.map((node_id) => ({ workspace_id: "study", node_id })),
    });
    expect(useUiStore.getState()).toMatchObject(selected);
    expect(JSON.stringify(useCanvasStore.getState().nodes)).toBe(before);
    expect(useCanvasStore.getState().version).toBe(7);
    expect(patch).not.toHaveBeenCalled();
  });

  it.each([422, 200])("retains a rejected request and exact scope for retry (HTTP %i)", async (status) => {
    const request = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: "invalid_request", message: "A selected target no longer exists" }), { status }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ intent: { id: "retry" } }), { status: 200 }));
    vi.stubGlobal("fetch", request);
    render(<SelectionAskDialog workspaceSlug="study" targetIds={["pump", "limits"]} onClose={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Check these two" } });
    fireEvent.click(screen.getByRole("button", { name: "Send to agent" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("A selected target no longer exists"));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("Check these two");
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Send to agent" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("2 selected nodes"));
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[1]![1].body).toBe(request.mock.calls[0]![1].body);
  });

  it("keeps typing local, ignores blank/IME submissions and consumes repeated pending sends once", async () => {
    let finish!: (response: Response) => void;
    const request = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", request);
    const onClose = vi.fn();
    render(<SelectionAskDialog workspaceSlug="study" targetIds={["pump"]} onClose={onClose} />);
    const text = screen.getByRole("textbox");
    const form = text.closest("form")!;
    fireEvent.submit(form);
    expect(request).not.toHaveBeenCalled();
    const outsideKey = vi.fn();
    window.addEventListener("keydown", outsideKey);
    try {
      fireEvent.keyDown(text, { key: "h" });
      fireEvent.keyDown(text, { key: "r" });
      fireEvent.keyDown(text, { key: "Delete" });
      expect(outsideKey).not.toHaveBeenCalled();
      fireEvent.change(text, { target: { value: "Ask about pump" } });
      fireEvent.keyDown(text, { key: "Enter", shiftKey: true });
      fireEvent.keyDown(text, { key: "Enter", isComposing: true });
      expect(request).not.toHaveBeenCalled();
      fireEvent.keyDown(text, { key: "Enter" });
      fireEvent.submit(form);
      expect(request).toHaveBeenCalledOnce();
      fireEvent.keyDown(text, { key: "Escape" });
      expect(onClose).not.toHaveBeenCalled();
      await act(async () => { finish(new Response(JSON.stringify({ intent: { id: "pending" } }), { status: 200 })); });
      expect(screen.getByRole("status").textContent).toContain("Request queued");
    } finally { window.removeEventListener("keydown", outsideKey); }
  });

  it("cancels without creating a request", () => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request);
    const onClose = vi.fn();
    render(<SelectionAskDialog workspaceSlug="study" targetIds={["pump"]} onClose={onClose} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Unsent request" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(request).not.toHaveBeenCalled();
  });
});
