import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DocumentIndex } from "@/api/documents";

import { PdfNavigationRail } from "./PdfNavigationRail";
import type { PdfDoc } from "./pdfjs";

const index: DocumentIndex = {
  document: { title: "Manual", filename: "manual.pdf", page_count: 6 },
  outline: [
    { title: "Introduction", level: 1, page: 1, bbox: [10, 10, 80, 20] },
    { title: "Operating limits", level: 2, page: 3, bbox: [10, 40, 80, 50] },
    { title: "Pressure", level: 3, page: 4, bbox: [10, 40, 80, 50] },
    { title: "Maintenance", level: 1, page: 6, bbox: [10, 10, 80, 20] },
  ],
  tables: [{ caption: "Operating data", page: 4, bbox: [10, 50, 80, 100] }],
  figures: [{ page: 5, bbox: [10, 50, 80, 100] }],
};

function bookmark(title: string, dest: unknown, items: unknown[] = []) {
  return { title, dest, items };
}

function pdf(outline: unknown[] | null = []) {
  return {
    numPages: 6,
    getOutline: vi.fn().mockResolvedValue(outline),
    getDestination: vi.fn().mockResolvedValue([{ num: 8, gen: 0 }]),
    getPageIndex: vi.fn().mockResolvedValue(3),
  } as unknown as PdfDoc;
}

describe("PDF contents navigation", () => {
  it("prefers silver headings, nests levels, and separates tables and figures", () => {
    const doc = pdf([bookmark("Embedded alternative", [2])]);
    const onNavigate = vi.fn();
    render(<PdfNavigationRail slug="manual" page={1} total={6} index={index} pdf={doc} onNavigate={onNavigate} />);
    expect(screen.getAllByTestId("thumbnail")).toHaveLength(6);
    fireEvent.click(screen.getByRole("tab", { name: "Contents" }));
    const intro = screen.getByRole("button", { name: "Introduction 1" });
    const limits = screen.getByRole("button", { name: "Operating limits 3" });
    expect(intro.closest("li")?.contains(limits)).toBe(true);
    expect(limits.closest("li")?.contains(screen.getByRole("button", { name: "Pressure 4" }))).toBe(true);
    expect(intro.closest("li")?.contains(screen.getByRole("button", { name: "Maintenance 6" }))).toBe(false);
    fireEvent.click(limits);
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ page: 3, bbox: [10, 40, 80, 50] }));
    expect(within(screen.getByRole("region", { name: "Tables" })).getByRole("button", { name: "Table 1: Operating data 4" })).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Figures" })).getByRole("button", { name: "Figure 1 5" })).toBeTruthy();
    expect(doc.getOutline).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Contents" }), { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Pages" }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Pages" }));
  });

  it("resolves embedded named destinations, indirect refs, and zero-based pages", async () => {
    const doc = pdf([
      bookmark("Chapter", null, [bookmark("Named section", "pressure"), bookmark("Direct page", [1])]),
      bookmark("Broken", "missing"), bookmark("External", null),
    ]);
    vi.mocked(doc.getDestination).mockImplementation(async (name) => {
      if (name === "missing") throw new Error("Missing destination");
      return [{ num: 8, gen: 0 }];
    });
    const onNavigate = vi.fn();
    render(<PdfNavigationRail slug="manual" page={1} total={6} index={{ ...index, outline: [] }} pdf={doc} initialTab="contents" onNavigate={onNavigate} />);
    const named = await screen.findByRole("button", { name: "Named section 4" });
    fireEvent.click(named);
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ page: 4 }));
    expect(doc.getPageIndex).toHaveBeenCalledWith({ num: 8, gen: 0 });
    expect(screen.getByRole("button", { name: "Direct page 2" })).toBeTruthy();
    expect(screen.getByText("Chapter").closest("li")?.contains(named)).toBe(true);
    expect(screen.queryByText("External")).toBeNull();
    expect(screen.queryByText("Broken")).toBeNull();
  });

  it.each([false, true])("keeps Pages available for missing or unreadable bookmarks (error=%s)", async (error) => {
    const doc = pdf(null);
    if (error) vi.mocked(doc.getOutline).mockRejectedValue(new Error("Unreadable outline"));
    render(<PdfNavigationRail slug="manual" page={1} total={6} index={{ ...index, outline: [], tables: [], figures: [] }} pdf={doc} initialTab="contents" onNavigate={vi.fn()} />);
    expect(await screen.findByText("No contents available. Use Pages to browse this document.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Pages" }));
    expect(screen.getAllByTestId("thumbnail")).toHaveLength(6);
  });

  it("ignores a late bookmark result from the previous document", async () => {
    const old = pdf();
    let resolve!: (outline: Awaited<ReturnType<PdfDoc["getOutline"]>>) => void;
    vi.mocked(old.getOutline).mockReturnValue(new Promise((done) => { resolve = done; }));
    const props = { page: 1, total: 6, initialTab: "contents" as const, onNavigate: vi.fn() };
    const view = render(<PdfNavigationRail {...props} slug="old" pdf={old} />);
    view.rerender(<PdfNavigationRail {...props} slug="new" pdf={pdf([bookmark("New chapter", [2])])} />);
    expect(await screen.findByRole("button", { name: "New chapter 3" })).toBeTruthy();
    await act(async () => { resolve([bookmark("Old chapter", [1])] as Awaited<ReturnType<PdfDoc["getOutline"]>>); });
    await waitFor(() => expect(screen.queryByText("Old chapter")).toBeNull());
  });

  it("omits out-of-range index targets and refuses malformed highlight boxes", () => {
    const invalid: DocumentIndex = { ...index, outline: [
      { title: "Missing page", level: 1, page: 99, bbox: [1, 2, 3, 4] },
      { title: "Valid page", level: 1, page: 3, bbox: [80, 50, 10, 40] },
    ] };
    const onNavigate = vi.fn();
    render(<PdfNavigationRail slug="manual" page={1} total={6} index={invalid} pdf={pdf()} initialTab="contents" onNavigate={onNavigate} />);
    expect(screen.queryByText("Missing page")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Valid page 3" }));
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({ page: 3, bbox: undefined }));
  });
});
