import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import { intents, type Intent } from "@/api/intents";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";
import { NodeDetailPanel } from "./NodeDetailPanel";

vi.mock("@/api/intents", () => ({ intents: { listAll: vi.fn() }, INTENTS_CHANGED_EVENT: "anchor:intents-changed" }));

const request = (id: string, workspace_id: string, node_id: string): Intent => ({
  id, kind: "user_request", origin_canvas_id: workspace_id, target: null,
  payload: { text: `Request ${id}` }, status: "resolved", created_at: 1,
  targets: [{ workspace_id, node_id }], items: [{ id: `${id}-reply`, type: "suggestion",
    author: { kind: "agent", label: "Researcher" }, text: "Checked the cited limit", created_at: 2, state: "approved" }],
});

function mount(readOnly = false) {
  return render(<MemoryRouter><NodeDetailPanel workspaceSlug="w1" nodeId="fact" onClose={vi.fn()} readOnly={readOnly} /></MemoryRouter>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(intents.listAll).mockResolvedValue([request("one", "w1", "fact"), request("other", "w2", "fact"), request("unrelated", "w1", "another")]);
  useCanvasStore.setState({
    nodes: {
      fact: { id: "fact", node_type: "fact", label: "Operating limit", x: 20, y: 30,
        data: { text: "First line\nComplete second line", rows: [{ key: "Speed", value: "5000 rpm" }],
          source_ref: { slug: "manual", page: 2, region_id: "r1" }, review: { state: "accepted", by: { kind: "human" } } } },
      doc: { id: "doc", node_type: "document", label: "Manual", x: 0, y: 0, data: { slug: "manual" } },
    },
    edges: { evidence: { id: "evidence", source: "fact", target: "doc", label: "Supported by manual", edge_type: "anchored", data: { kind: "evidence", source_ref: { page: 2 } } } },
  });
  useUiStore.setState({ pdfViewer: null });
  vi.spyOn(documents, "resolveRef").mockResolvedValue({ slug: "manual", page: 2, bbox: [10, 20, 100, 80], precision: "region" });
});

describe("node read details", () => {
  it("shows full content, rows, evidence, review and only this node's targeted thread", async () => {
    mount();
    expect(screen.getAllByText(/Complete second line/).length).toBeGreaterThan(0);
    expect(screen.getByText("5000 rpm")).toBeTruthy();
    expect(screen.getByText("Supported by manual")).toBeTruthy();
    expect(screen.getAllByText(/"state": "accepted"/).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("Request one")).toBeTruthy());
    expect(screen.getByText("Checked the cited limit")).toBeTruthy();
    expect(screen.getAllByText(/approved/).length).toBeGreaterThan(0);
    expect(screen.getByText("Full thread item")).toBeTruthy();
    expect(screen.queryByText("Request other")).toBeNull();
    expect(screen.queryByText("Request unrelated")).toBeNull();
  });

  it("resolves the source crop and opens the viewer on the same cited box", async () => {
    mount();
    await waitFor(() => {
      const crop = screen.getByAltText("Source 1: manual, page 2");
      expect(crop.getAttribute("src")).toContain("bbox=10%2C20%2C100%2C80");
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Open viewer at page 2" })[0]!);
    await waitFor(() => expect(useUiStore.getState().pdfViewer).toMatchObject({ slug: "manual", page: 2, highlightBbox: [10, 20, 100, 80] }));
  });

  it("resolves selector-only sources and handles failed preview resolution", async () => {
    useCanvasStore.setState((state) => ({ nodes: { ...state.nodes, fact: { ...state.nodes.fact!, data: { source_ref: { slug: "manual", region_id: "r1" } } } }, edges: {} }));
    vi.mocked(documents.resolveRef).mockResolvedValueOnce({ slug: "manual", page: 4, bbox: [0, 0, 40, 40], precision: "region" });
    mount(true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Open viewer at page 4" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Edit properties" })).toBeNull();
    expect(screen.queryByLabelText("Node presentation")).toBeNull();
  });

  it("keeps source opening available when crop resolution fails", async () => {
    vi.mocked(documents.resolveRef).mockRejectedValue(new Error("Unavailable"));
    mount();
    await waitFor(() => expect(screen.getAllByText("Source preview unavailable.").length).toBeGreaterThan(0));
    expect(screen.getAllByRole("button", { name: "Open viewer at page 2" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Open viewer at page 2" })[0]!);
    expect(useUiStore.getState().pdfViewer).toMatchObject({ slug: "manual", page: 2 });
  });

  it("resolves page-only legacy row refs through a document card and keeps another row's slug independent", async () => {
    useCanvasStore.setState((state) => ({ nodes: { ...state.nodes, fact: { ...state.nodes.fact!, node_type: "spec", data: {
      source_doc_node_id: "doc", source_region_id: "manual-region", rows: [
        { key: "Legacy", value: "10", source_ref: { page: 2 } },
        { key: "Other document", value: "20", source_ref: { slug: "other", page: 3 } },
      ],
    } } }, edges: {} }));
    mount();
    expect(screen.getByRole("button", { name: "Open source for Legacy" })).toBeTruthy();
    expect(screen.getByAltText(/other, page 3/)).toBeTruthy();
    await waitFor(() => expect(documents.resolveRef).toHaveBeenCalledWith("manual", expect.objectContaining({ region_id: "manual-region" })));
    expect(vi.mocked(documents.resolveRef).mock.calls.some(([slug]) => slug === "other")).toBe(false);
    expect(screen.getByAltText(/other, page 3/).getAttribute("src")).toContain("other/pages/3/image");
  });

  it("does not turn a non-document node's slug into a legacy source", async () => {
    useCanvasStore.setState((state) => ({ nodes: { ...state.nodes,
      doc: { ...state.nodes.doc!, node_type: "spec" },
      fact: { ...state.nodes.fact!, data: { source_doc_node_id: "doc", source_ref: { doc_id: "doc", page: 2 }, rows: [{ key: "Value", value: "10", source_ref: { page: 2 } }] } },
    }, edges: {} }));
    mount();
    expect(screen.queryByLabelText("Node sources")).toBeNull();
    expect(screen.queryByRole("button", { name: "Open source for Value" })).toBeNull();
    await waitFor(() => expect(screen.getByText("Request one")).toBeTruthy());
  });

  it("renders Markdown anchor links safely in the detail view", async () => {
    useCanvasStore.setState((state) => ({ nodes: { ...state.nodes, fact: { ...state.nodes.fact!, node_type: "markdown",
      data: { text: "See [limit](anchor:manual?page=2). [bad](javascript:alert%281%29)" } } }, edges: {} }));
    mount();
    fireEvent.click(screen.getByTestId("source-ref-link"));
    expect(useUiStore.getState().pdfViewer?.page).toBe(2);
    expect(screen.getByText("bad").getAttribute("href")).not.toContain("javascript:");
    await waitFor(() => expect(intents.listAll).toHaveBeenCalled());
  });
});
