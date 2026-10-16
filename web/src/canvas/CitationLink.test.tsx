import { act, fireEvent, render, screen } from "@testing-library/react";
import Markdown from "react-markdown";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnchoredText } from "@/canvas/AnchoredText";
import { formatReferenceHref, parseReferenceHref } from "@/canvas/anchorHref";
import { markdownComponents, urlTransform } from "@/canvas/shapes/MarkdownNode";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

const source = { slug: "norrhavn-px", page: 1, bbox: [20, 30, 100, 60], detail: { quote: "10" } };
const reference = { id: "ref-1", source_ref: source, label: "Rated pressure", created_by: "human" as const, created_at: 1 };
beforeEach(() => {
  useCanvasStore.getState().reset();
  useCanvasStore.getState().setSnapshot({ slug: "board", title: "", version: 1, nodes: [], edges: [], metadata: { references: [reference] } });
});
afterEach(() => vi.restoreAllMocks());

describe("bibliography citations", () => {
  it("round-trips IDs and rejects malformed or document links", () => {
    expect(parseReferenceHref(formatReferenceHref("ref-1"))).toBe("ref-1");
    for (const href of ["anchor:ref/", "anchor:ref/%", "anchor:ref/a%2Fb", "anchor:ref/a?page=1", "anchor:doc?page=1"]) {
      expect(parseReferenceHref(href)).toBeNull();
    }
  });

  it("opens the stored locator from plain text and follows live deletion", () => {
    const openPdf = vi.spyOn(useUiStore.getState(), "openPdf");
    render(<MemoryRouter><AnchoredText workspaceSlug="board" text="Rated at [10 bar](anchor:ref/ref-1)." /></MemoryRouter>);
    fireEvent.click(screen.getByTestId("source-ref-link"));
    expect(openPdf).toHaveBeenCalledWith("norrhavn-px", expect.objectContaining({ page: 1, highlightBbox: source.bbox, highlightQuery: "10" }));
    act(() => useCanvasStore.getState().applyEvent({ id: "e2", type: "ReferenceRemoved", workspace_id: "board", version: 2, payload: { reference_id: "ref-1" }, ts: 0 }));
    expect(screen.getByTestId("source-ref-broken").textContent).toBe("10 bar");
    expect(screen.queryByTestId("source-ref-link")).toBeNull();
  });

  it("resolves the same ID in Markdown without enabling raw HTML", () => {
    const { container } = render(<Markdown components={markdownComponents("board")} urlTransform={urlTransform}>{"[10 bar](anchor:ref/ref-1) <script>alert(1)</script>"}</Markdown>);
    expect(screen.getByTestId("source-ref-link").textContent).toContain("10 bar");
    expect(container.querySelector("script")).toBeNull();
  });

  it("never resolves an ID from another canvas", () => {
    render(<MemoryRouter><AnchoredText workspaceSlug="other" text="[10 bar](anchor:ref/ref-1)" /></MemoryRouter>);
    expect(screen.getByTestId("source-ref-broken")).toBeTruthy();
  });
});
