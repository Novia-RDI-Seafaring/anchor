/**
 * ReferencesPanel tests (#147 slice 3).
 *
 * Pins the panel contract at the component boundary: it lists the canvas
 * bibliography, opens a reference's source in the PDF dock at page + bbox
 * (+ quote highlight), deletes an entry, and renames its label. The
 * references API is stubbed so the tests run without a backend.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { references } from "@/api/references";
import type { Reference } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { ReferencesPanel } from "./ReferencesPanel";

const REFS: Reference[] = [
  {
    id: "ref-1",
    label: "Max inlet pressure",
    source_ref: {
      slug: "datasheet",
      page: 3,
      bbox: [10, 20, 30, 40],
      detail: { quote: "max 5 bar" },
    },
    created_by: "human",
    created_at: 1,
  },
  {
    id: "ref-2",
    source_ref: { slug: "manual", page: 7 },
    created_by: "agent",
    created_at: 2,
  },
];

beforeEach(() => {
  useUiStore.setState({ pdfViewer: null });
  vi.spyOn(references, "list").mockResolvedValue(structuredClone(REFS));
});

afterEach(() => {
  vi.restoreAllMocks();
  useUiStore.setState({ pdfViewer: null });
});

async function renderPanel() {
  await act(async () => {
    render(<ReferencesPanel canvasSlug="canvas-1" />);
  });
}

describe("ReferencesPanel", () => {
  it("lists the canvas references with label, slug, page, and quote", async () => {
    await renderPanel();
    await waitFor(() => expect(references.list).toHaveBeenCalledWith("canvas-1"));
    const rows = await screen.findAllByTestId("reference-row");
    expect(rows).toHaveLength(2);
    expect(screen.getByText("Max inlet pressure")).toBeTruthy();
    // Row 2 has no label -> falls back to slug · page.
    expect(screen.getByText("manual · p.7")).toBeTruthy();
    // Quote snippet renders for the bbox row.
    expect(screen.getByText(/max 5 bar/)).toBeTruthy();
  });

  it("renders a crop thumbnail only when a bbox is present", async () => {
    const { container } = render(<ReferencesPanel canvasSlug="canvas-1" />);
    await screen.findAllByTestId("reference-row");
    const imgs = container.querySelectorAll("img");
    // Only ref-1 has a bbox -> one thumbnail.
    expect(imgs).toHaveLength(1);
    expect(imgs[0]!.getAttribute("src")).toContain("/api/documents/datasheet/pages/3/crop");
  });

  it("opens the source in the dock at page + bbox + quote on click", async () => {
    const openPdf = vi.fn();
    useUiStore.setState({ openPdf });
    await renderPanel();
    const opens = await screen.findAllByTestId("reference-open");
    fireEvent.click(opens[0]!);
    expect(openPdf).toHaveBeenCalledWith("datasheet", {
      page: 3,
      mode: "dock",
      workspaceSlug: "canvas-1",
      highlightRegionId: undefined,
      highlightBbox: [10, 20, 30, 40],
      highlightQuery: "max 5 bar",
    });
  });

  it("deletes a reference", async () => {
    const remove = vi.spyOn(references, "remove").mockResolvedValue(undefined);
    await renderPanel();
    const dels = await screen.findAllByTestId("reference-delete");
    await act(async () => {
      fireEvent.click(dels[0]!);
    });
    expect(remove).toHaveBeenCalledWith("canvas-1", "ref-1");
    // Optimistic removal: the row is gone.
    await waitFor(() =>
      expect(screen.queryByText("Max inlet pressure")).toBeNull(),
    );
  });

  it("renames a reference label", async () => {
    const update = vi.spyOn(references, "update").mockResolvedValue(undefined);
    await renderPanel();
    const renames = await screen.findAllByTestId("reference-rename");
    fireEvent.click(renames[0]!);
    const input = await screen.findByTestId("reference-label-input");
    fireEvent.change(input, { target: { value: "Renamed caption" } });
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter" });
    });
    expect(update).toHaveBeenCalledWith("canvas-1", "ref-1", {
      label: "Renamed caption",
    });
  });

  it("refetches when a references-changed event fires for this canvas", async () => {
    await renderPanel();
    await waitFor(() => expect(references.list).toHaveBeenCalledTimes(1));
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent("anchor:references-changed", {
          detail: { slug: "canvas-1" },
        }),
      );
    });
    await waitFor(() => expect(references.list).toHaveBeenCalledTimes(2));
  });

  it("ignores references-changed events for other canvases", async () => {
    await renderPanel();
    await waitFor(() => expect(references.list).toHaveBeenCalledTimes(1));
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent("anchor:references-changed", {
          detail: { slug: "other-canvas" },
        }),
      );
    });
    // No extra fetch for a different canvas.
    expect(references.list).toHaveBeenCalledTimes(1);
  });
});
