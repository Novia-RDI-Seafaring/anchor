/**
 * Judging a reference means looking at the source while you decide. The menu
 * opens on a right-click on the anchor, stays until a click lands outside it,
 * and holds the source pane for as long as it is open.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RefReviewChip } from "@/canvas/RefReviewChip";
import { scheduleTransientClose, TRANSIENT_CLOSE_MS } from "@/canvas/transientViewer";
import { useUiStore } from "@/stores/uiStore";

function openTransientPane() {
  useUiStore.getState().openPdf("lkh", { page: 3, transient: true });
  useUiStore.setState({ pdfViewerPinned: false, hoverPreviewMode: "viewer" });
}

const wait = (ms: number) =>
  act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });

function renderChip(onChange = vi.fn(), review: Parameters<typeof RefReviewChip>[0]["review"] = null) {
  render(
    <RefReviewChip label="B" review={review} onChange={onChange}>
      <button type="button">anchor</button>
    </RefReviewChip>,
  );
  return onChange;
}

beforeEach(() => {
  useUiStore.setState({ pdfViewer: null, pdfViewerPinned: false, hoverPreviewMode: "viewer" });
});

describe("opening and closing the menu", () => {
  it("opens on a right-click on the anchor, not on hover or a click", async () => {
    renderChip();
    const chip = screen.getByTestId("ref-review-chip");
    fireEvent.mouseEnter(chip);
    await wait(200);
    fireEvent.click(chip);
    expect(screen.queryByTestId("ref-review-menu")).toBeNull();
    fireEvent.contextMenu(chip, { clientX: 100, clientY: 100 });
    expect(screen.getByTestId("ref-review-menu")).toBeTruthy();
  });

  it("stays when the pointer leaves the anchor", async () => {
    renderChip();
    const chip = screen.getByTestId("ref-review-chip");
    fireEvent.contextMenu(chip);
    fireEvent.mouseLeave(chip);
    await wait(400);
    expect(screen.getByTestId("ref-review-menu")).toBeTruthy();
  });

  it("goes on a click outside it", async () => {
    renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.mouseDown(document.body);
    await waitFor(() => expect(screen.queryByTestId("ref-review-menu")).toBeNull());
  });

  it("closes once a choice is made, as a menu does", async () => {
    const onChange = renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.click(screen.getByTestId("ref-review-accept"));
    expect(onChange).toHaveBeenCalledWith("accepted", "");
    expect(screen.queryByTestId("ref-review-menu")).toBeNull();
  });

  it("does not close while the note is being typed", async () => {
    renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.change(screen.getByTestId("ref-review-note"), { target: { value: "wrong row" } });
    expect(screen.getByTestId("ref-review-menu")).toBeTruthy();
  });
});

describe("keys", () => {
  it("y accepts and n rejects while the menu is open, and each closes it", async () => {
    const onChange = renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.keyDown(window, { key: "y" });
    expect(onChange).toHaveBeenLastCalledWith("accepted", "");
    expect(screen.queryByTestId("ref-review-menu")).toBeNull();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.keyDown(window, { key: "n" });
    expect(onChange).toHaveBeenLastCalledWith("rejected", "");
  });

  it("dismisses on Escape rather than destroying the verdict", async () => {
    // Escape means "get me out of here" everywhere else. Having it delete a
    // judgement was a surprising thing for that key to do.
    const onChange = renderChip(vi.fn(), { state: "accepted" });
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    expect(screen.getByTestId("ref-review-menu")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("ref-review-menu")).toBeNull());
  });

  it("takes a verdict back when the one already chosen is chosen again", async () => {
    // Two buttons instead of three and a Clear: the lit one unsets itself.
    const onChange = renderChip(vi.fn(), { state: "accepted" });
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.click(screen.getByTestId("ref-review-accept"));
    expect(onChange).toHaveBeenLastCalledWith(null, undefined);
  });

  it("switches straight from one verdict to the other", async () => {
    const onChange = renderChip(vi.fn(), { state: "accepted" });
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.click(screen.getByTestId("ref-review-reject"));
    expect(onChange).toHaveBeenLastCalledWith("rejected", "");
  });

  it("toggles off by keyboard too", async () => {
    const onChange = renderChip(vi.fn(), { state: "rejected" });
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.keyDown(window, { key: "n" });
    expect(onChange).toHaveBeenLastCalledWith(null, undefined);
  });

  it("saves a note against its verdict without disturbing it", async () => {
    const onChange = renderChip(vi.fn(), { state: "rejected" });
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    const note = screen.getByTestId("ref-review-note");
    fireEvent.change(note, { target: { value: "points at J2" } });
    fireEvent.keyDown(note, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith("rejected", "points at J2");
  });

  it("ignores the keys when the menu is closed", () => {
    const onChange = renderChip();
    fireEvent.keyDown(window, { key: "y" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("leaves typing in the note alone", () => {
    const onChange = renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    const note = screen.getByTestId("ref-review-note");
    fireEvent.keyDown(note, { key: "n" });
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("the mark", () => {
  it("shows nothing for an unjudged reference", () => {
    renderChip();
    expect(screen.queryByTestId("ref-review-mark")).toBeNull();
    expect(screen.getByTestId("ref-review-chip").getAttribute("data-state")).toBe("unjudged");
  });

  it("shows the verdict in the corner, with a note mark when there is one", () => {
    renderChip(vi.fn(), { state: "rejected", note: "wrong field" });
    expect(screen.getByTestId("ref-review-mark").textContent).toContain("✕");
    expect(screen.getByTestId("ref-review-has-note")).toBeTruthy();
    expect(screen.getByTestId("ref-review-chip").getAttribute("data-state")).toBe("rejected");
  });
});

describe("RefReviewChip and the source pane", () => {
  it("keeps the source while the menu is open, through a note", async () => {
    openTransientPane();
    renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.change(screen.getByTestId("ref-review-note"), { target: { value: "checking" } });
    scheduleTransientClose();
    await wait(TRANSIENT_CLOSE_MS + 120);
    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });

  it("lets the source go once the menu is put away", async () => {
    openTransientPane();
    renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    // Leaving the menu no longer closes it: it is a context menu now.
    fireEvent.mouseLeave(screen.getByTestId("ref-review-menu"));
    await wait(400);
    expect(screen.getByTestId("ref-review-menu")).toBeTruthy();
    // A click outside puts it away, and the source goes with it.
    fireEvent.mouseDown(document.body);
    await wait(50);
    await wait(TRANSIENT_CLOSE_MS + 120);
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("lets the source go when the pointer leaves the anchor without the menu opening", async () => {
    openTransientPane();
    renderChip();
    const chip = screen.getByTestId("ref-review-chip");
    fireEvent.mouseEnter(chip);
    fireEvent.mouseLeave(chip);
    scheduleTransientClose();
    await wait(TRANSIENT_CLOSE_MS + 120);
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("never closes a pane the reader clicked open", async () => {
    useUiStore.getState().openPdf("lkh", { page: 3 });
    expect(useUiStore.getState().pdfViewerPinned).toBe(true);
    renderChip();
    fireEvent.contextMenu(screen.getByTestId("ref-review-chip"));
    fireEvent.mouseLeave(screen.getByTestId("ref-review-menu"));
    // Two waits: the menu's leave timer, then the pane's own close timer,
    // which is only armed once React has run the effect cleanup.
    await wait(400);
    await wait(TRANSIENT_CLOSE_MS + 120);
    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });
});
