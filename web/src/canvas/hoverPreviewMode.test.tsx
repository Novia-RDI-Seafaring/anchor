/**
 * Two ways to answer "what is at the other end of this link", kept side by
 * side so they can be compared rather than argued about. These pin the part
 * that is easy to get wrong: a pane opened by a hover must go away again, and
 * a pane the user clicked open must not.
 */
import { fireEvent, render, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SourceRefLink } from "@/canvas/SourceRefLink";
import {
  cancelTransientClose,
  scheduleTransientClose,
  TRANSIENT_CLOSE_MS,
} from "@/canvas/transientViewer";
import { HoverPreviewToggle } from "@/shell/HoverPreviewToggle";
import { useUiStore } from "@/stores/uiStore";

// Whether a document card for this ref is on the canvas and visible. The real
// one asks the rendered canvas; here it is a switch, so the preference can be
// tested without standing up React Flow.
let cardInView = false;
vi.mock("@/canvas/useOpenSourceRef", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/canvas/useOpenSourceRef")>()),
  documentCardInView: () => cardInView,
}));

const REF = { slug: "lkh", page: 3, bbox: [1, 2, 3, 4] };

function drawLink() {
  return render(
    <MemoryRouter>
      <SourceRefLink workspaceSlug="board" refValue={REF}>24 m</SourceRefLink>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  cardInView = false;
  useUiStore.setState({
    pdfViewer: null,
    pdfViewerPinned: false,
    hoverPreviewMode: "panel",
    hoveredSourceRef: null,
  });
});

describe("an already-open pane", () => {
  it("keeps the next hover, even though a card is showing the document", async () => {
    // The reader opened it and is looking at it. Lighting up a card behind the
    // pane answers a question they are not asking.
    cardInView = true;
    useUiStore.getState().openPdf("other-doc", { page: 1 });
    expect(useUiStore.getState().pdfViewerPinned).toBe(true);

    const user = userEvent.setup();
    const { container } = drawLink();
    await user.hover(container.querySelector('[data-testid="source-ref-link"]')!);

    // The pane swapped document in place rather than staying on the old one.
    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
  });

  it("stays open after the pointer leaves, because it was clicked open", async () => {
    cardInView = true;
    useUiStore.getState().openPdf("other-doc", { page: 1 });
    const user = userEvent.setup();
    const { container } = drawLink();
    const link = container.querySelector('[data-testid="source-ref-link"]')!;

    await user.hover(link);
    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
    expect(useUiStore.getState().pdfViewerPinned).toBe(true);

    await user.unhover(link);
    await new Promise((r) => setTimeout(r, 300));
    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });

  it("moves the pane in panel mode too, rather than adding a crop beside the link", async () => {
    useUiStore.setState({ hoverPreviewMode: "panel" });
    useUiStore.getState().openPdf("other-doc", { page: 1 });
    const user = userEvent.setup();
    const { container } = drawLink();
    await user.hover(container.querySelector('[data-testid="source-ref-link"]')!);

    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
    expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeNull();
  });
});

describe("a document already on the canvas", () => {
  it("is lit up in place rather than opened a second time", async () => {
    // Covering a document the reader can already see with another copy of it
    // is the worst of both, and it costs them the canvas they arranged.
    cardInView = true;
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const user = userEvent.setup();
    const { container } = drawLink();
    await user.hover(container.querySelector('[data-testid="source-ref-link"]')!);
    await new Promise((r) => setTimeout(r, 400));

    expect(useUiStore.getState().pdfViewer).toBeNull();
    expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeNull();
    // The card is told where to look.
    expect(useUiStore.getState().hoveredSourceRef).toMatchObject({ slug: "lkh", page: 3 });
  });

  it("opens the pane anyway when no card is showing it", async () => {
    cardInView = false;
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const user = userEvent.setup();
    const { container } = drawLink();
    await user.hover(container.querySelector('[data-testid="source-ref-link"]')!);

    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
  });

  it("still opens the pane on a click, because a click is a commitment", async () => {
    cardInView = true;
    const user = userEvent.setup();
    const { container } = drawLink();
    await user.click(container.querySelector('[data-testid="source-ref-link"]')!);

    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
  });
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

describe("a ref that arrives under a still pointer", () => {
  it("does not open on a bare mouseenter with no movement", async () => {
    // As the pane fades out it uncovers the link that opened it, and the link
    // gets a mouseenter the reader never performed. Acting on it reopened the
    // pane mid-fade: the flicker on mouse-out, with a second round of page and
    // region requests behind it.
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const { container } = drawLink();
    const link = container.querySelector('[data-testid="source-ref-link"]')!;

    fireEvent.mouseEnter(link);
    await new Promise((r) => setTimeout(r, 300));

    expect(useUiStore.getState().pdfViewer).toBeNull();
    expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeNull();
  });

  it("opens as soon as the pointer actually moves over it", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    const { container } = drawLink();
    const link = container.querySelector('[data-testid="source-ref-link"]')!;

    fireEvent.mouseEnter(link);
    fireEvent.mouseMove(link);

    await waitFor(() => expect(useUiStore.getState().pdfViewer?.slug).toBe("lkh"));
  });
});

describe("reaching a hover-opened pane", () => {
  it("survives the trip: entering the pane cancels the pending close", async () => {
    // The pane opens on the far left while the link is out in the canvas, so
    // reading it means leaving the link. When the close timer lived in the
    // link, the pane vanished before the pointer could arrive.
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    useUiStore.getState().openPdf("lkh", { page: 3, transient: true });
    useUiStore.setState({ pdfViewerPinned: false });

    scheduleTransientClose();
    cancelTransientClose();
    await new Promise((r) => setTimeout(r, TRANSIENT_CLOSE_MS + 120));

    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });

  it("closes once the pointer is on neither the link nor the pane", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    useUiStore.getState().openPdf("lkh", { page: 3, transient: true });
    useUiStore.setState({ pdfViewerPinned: false });

    scheduleTransientClose();
    await new Promise((r) => setTimeout(r, TRANSIENT_CLOSE_MS + 120));

    expect(useUiStore.getState().pdfViewer).toBeNull();
  });

  it("allows time to cross the canvas, not just to twitch", () => {
    // A debounce would be tens of milliseconds. This is a journey.
    expect(TRANSIENT_CLOSE_MS).toBeGreaterThanOrEqual(400);
  });

  it("never closes a pinned pane, however long the pointer is away", async () => {
    useUiStore.setState({ hoverPreviewMode: "viewer" });
    useUiStore.getState().openPdf("lkh", { page: 3 });
    expect(useUiStore.getState().pdfViewerPinned).toBe(true);

    scheduleTransientClose();
    await new Promise((r) => setTimeout(r, TRANSIENT_CLOSE_MS + 120));

    expect(useUiStore.getState().pdfViewer).not.toBeNull();
  });

  it("leaves the pane alone in panel mode", async () => {
    useUiStore.setState({ hoverPreviewMode: "panel" });
    useUiStore.getState().openPdf("lkh", { page: 3, transient: true });
    useUiStore.setState({ pdfViewerPinned: false });

    scheduleTransientClose();
    await new Promise((r) => setTimeout(r, TRANSIENT_CLOSE_MS + 120));

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
