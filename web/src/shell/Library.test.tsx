/**
 * Library.test.tsx — smoke tests for the document disambiguation additions
 * (issue #127).
 *
 * Covers:
 *   1. Each document row renders the filename (secondary line) and carries
 *      the slug as a `title` attribute for tooltip disambiguation.
 *   2. The thumbnail <img> src points at the pageImageUrl for page 1.
 *   3. When the image errors, a fallback element appears instead of a broken
 *      <img>.
 *   4. Hovering the row shows a preview popover.
 */
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as docsApi from "@/api/documents";
import type { DocumentSummary } from "@/api/documents";
import * as cadApi from "@/api/cad";

import { Library } from "./Library";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDoc(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    slug: "my-pump-leaflet",
    title: "Pump Leaflet",
    filename: "pump_leaflet_v3.pdf",
    page_count: 12,
    has_gold: true,
    region_count: 42,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

function renderLibrary() {
  return render(<Library workspaceSlug="ws-1" />);
}

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

describe("Library document row identity", () => {
  it("renders filename as a secondary line under the title", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([
      makeDoc({ title: "Pump Leaflet", filename: "pump_leaflet_v3.pdf" }),
    ]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);

    renderLibrary();

    await waitFor(() => {
      expect(screen.getByText("Pump Leaflet")).toBeTruthy();
    });

    const filenameEl = screen.getByTestId("doc-filename");
    expect(filenameEl.textContent).toBe("pump_leaflet_v3.pdf");
  });

  it("exposes slug via title attribute for tooltip disambiguation", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([
      makeDoc({ slug: "pump-abc-123", title: "Pump Leaflet" }),
    ]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);

    const { container } = renderLibrary();

    await waitFor(() => {
      expect(screen.getByText("Pump Leaflet")).toBeTruthy();
    });

    const row = container.querySelector('[data-slug="pump-abc-123"]');
    expect(row).not.toBeNull();
    expect((row as HTMLElement).title).toBe("pump-abc-123");
  });

  it("makes two docs with identical titles visually distinguishable via filename", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([
      makeDoc({ slug: "doc-a", title: "Product Sheet", filename: "productA.pdf" }),
      makeDoc({ slug: "doc-b", title: "Product Sheet", filename: "productB.pdf" }),
    ]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);

    renderLibrary();

    await waitFor(() => {
      const items = screen.getAllByTestId("doc-filename");
      expect(items.length).toBe(2);
      const texts = items.map((el) => el.textContent);
      expect(texts).toContain("productA.pdf");
      expect(texts).toContain("productB.pdf");
    });
  });
});

describe("Library document thumbnail", () => {
  it("renders an img whose src is the page-1 image URL for the slug", async () => {
    const slug = "spec-doc-xyz";
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([
      makeDoc({ slug }),
    ]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);
    // Spy on pageImageUrl to confirm it is called with the right args.
    const pageImageUrlSpy = vi.spyOn(docsApi.documents, "pageImageUrl");

    renderLibrary();

    await waitFor(() => {
      expect(screen.getByTestId("thumbnail-img")).toBeTruthy();
    });

    expect(pageImageUrlSpy).toHaveBeenCalledWith(slug, 1);
    const img = screen.getByTestId("thumbnail-img") as HTMLImageElement;
    // The src must contain the slug so it is clearly doc-specific.
    expect(img.src).toContain(slug);
  });

  it("shows fallback element when thumbnail image errors, not a broken img", async () => {
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([
      makeDoc({ slug: "silver-only" }),
    ]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);

    renderLibrary();

    await waitFor(() => {
      expect(screen.getByTestId("thumbnail-img")).toBeTruthy();
    });

    const img = screen.getByTestId("thumbnail-img");
    // Simulate an image load failure (e.g. silver-only doc with no PNG).
    act(() => {
      fireEvent.error(img);
    });

    // Fallback box must appear; broken img must be gone.
    expect(screen.getByTestId("thumbnail-fallback")).toBeTruthy();
    expect(screen.queryByTestId("thumbnail-img")).toBeNull();
  });
});

describe("Library document hover preview", () => {
  it("shows a preview popover on mouseenter (after debounce) and hides on mouseleave", async () => {
    vi.useFakeTimers();
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([makeDoc()]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);

    renderLibrary();

    // Resolve the async list() calls with fake timers active.
    await act(async () => {
      await Promise.resolve();
    });

    const row = screen.getByTestId("document-item");

    // Preview must not be visible before hover.
    expect(screen.queryByTestId("hover-preview")).toBeNull();

    act(() => {
      fireEvent.mouseEnter(row);
    });
    // Before the debounce fires, preview is still hidden.
    expect(screen.queryByTestId("hover-preview")).toBeNull();

    // Advance the 300ms debounce.
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(screen.getByTestId("hover-preview")).toBeTruthy();

    act(() => {
      fireEvent.mouseLeave(row);
    });
    expect(screen.queryByTestId("hover-preview")).toBeNull();

    vi.useRealTimers();
  });

  it("toggles preview on right-click (context menu)", async () => {
    vi.useFakeTimers();
    vi.spyOn(docsApi.documents, "list").mockResolvedValue([makeDoc()]);
    vi.spyOn(cadApi.cad, "list").mockResolvedValue([]);

    renderLibrary();

    await act(async () => {
      await Promise.resolve();
    });

    const row = screen.getByTestId("document-item");
    expect(screen.queryByTestId("hover-preview")).toBeNull();

    act(() => {
      fireEvent.contextMenu(row);
    });
    expect(screen.getByTestId("hover-preview")).toBeTruthy();

    act(() => {
      fireEvent.contextMenu(row);
    });
    expect(screen.queryByTestId("hover-preview")).toBeNull();

    vi.useRealTimers();
  });
});
