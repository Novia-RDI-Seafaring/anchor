/**
 * Two ways to answer "what is at the other end of this link", kept side by
 * side so they can be compared rather than argued about. These pin the part
 * that is easy to get wrong: a pane opened by a hover must go away again, and
 * a pane the user clicked open must not.
 */
import { render, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { SourceRefLink } from "@/canvas/SourceRefLink";
import { HoverPreviewToggle } from "@/shell/HoverPreviewToggle";
import { useUiStore } from "@/stores/uiStore";

const REF = { slug: "lkh", page: 3, bbox: [1, 2, 3, 4] };

function drawLink() {
  return render(
    <MemoryRouter>
      <SourceRefLink workspaceSlug="board" refValue={REF}>24 m</SourceRefLink>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useUiStore.setState({ pdfViewer: null, pdfViewerPinned: false, hoverPreviewMode: "panel" });
});

describe("hover preview mode", () => {
  it("defaults to the small panel and leaves the viewer closed", async () => {
    const user = userEvent.setup();
    const { container } = drawLink();
    await user.hover(container.querySelector('[data-testid="source-ref-link"]')!);

    await waitFor(() =>
      expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeTruthy(),
    );
    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("in viewer mode, hovering opens the pane instead of a panel", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const user = userEvent.setup();
    const { container } = drawLink();
    await user.hover(container.querySelector('[data-testid="source-ref-link"]')!);

    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
    expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeNull();
  });

  it("a hover-opened pane is not pinned, so leaving takes it away", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const user = userEvent.setup();
    const { container } = drawLink();
    const link = container.querySelector('[data-testid="source-ref-link"]')!;

    await user.hover(link);
    await waitFor(() => expect(useUiStore.getState().pdfViewer).not.toBeNull());
    expect(useUiStore.getState().pdfViewerPinned).toBe(false);

    await user.unhover(link);
    await waitFor(() => expect(useUiStore.getState().pdfViewer).toBeNull());
  });

  it("clicking pins the pane, so it survives the pointer leaving", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const user = userEvent.setup();
    const { container } = drawLink();
    const link = container.querySelector('[data-testid="source-ref-link"]')!;

    await user.click(link);
    await waitFor(() => expect(useUiStore.getState().pdfViewerPinned).toBe(true));

    await user.unhover(link);
    // Given time to close if it were going to.
    await new Promise((r) => setTimeout(r, 300));
    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });

  it("a pane opened some other way is never closed by a passing hover", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    useUiStore.getState().openPdf("other-doc", { page: 1 });
    expect(useUiStore.getState().pdfViewerPinned).toBe(true);

    const user = userEvent.setup();
    const { container } = drawLink();
    const link = container.querySelector('[data-testid="source-ref-link"]')!;
    await user.hover(link);
    await user.unhover(link);
    await new Promise((r) => setTimeout(r, 300));

    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });
});

describe("HoverPreviewToggle", () => {
  it("switches the mode and says which one is live", async () => {
    const user = userEvent.setup();
    const { getByTestId } = render(<HoverPreviewToggle />);

    expect(getByTestId("hover-mode-panel").getAttribute("aria-pressed")).toBe("true");
    await user.click(getByTestId("hover-mode-viewer"));

    expect(useUiStore.getState().hoverPreviewMode).toBe("viewer");
    expect(getByTestId("hover-mode-viewer").getAttribute("aria-pressed")).toBe("true");
  });
});
