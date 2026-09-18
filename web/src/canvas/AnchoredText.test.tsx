import { render, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AnchoredText, splitAnchorLinks } from "@/canvas/AnchoredText";

function draw(text: string) {
  return render(
    <MemoryRouter>
      <AnchoredText text={text} workspaceSlug="board" />
    </MemoryRouter>,
  );
}

describe("splitAnchorLinks", () => {
  it("leaves a plain string in one piece", () => {
    expect(splitAnchorLinks("just words")).toEqual(["just words"]);
  });

  it("splits an anchor link out of its surrounding prose", () => {
    const parts = splitAnchorLinks("Head is [24 m](anchor:lkh?page=3) at duty.");
    expect(parts).toHaveLength(3);
    expect(parts[0]).toBe("Head is ");
    expect(typeof parts[1]).toBe("object");
    expect(parts[2]).toBe(" at duty.");
  });

  it("keeps a non-anchor link as literal text", () => {
    // An http link in a plain card is not a provenance claim.
    expect(splitAnchorLinks("see [docs](https://example.com)")).toEqual([
      "see [docs](https://example.com)",
    ]);
  });

  it("handles several links in one string", () => {
    const parts = splitAnchorLinks(
      "[a](anchor:d?page=1) and [b](anchor:d?page=2)",
    );
    expect(parts.filter((p) => typeof p === "object")).toHaveLength(2);
  });

  it("does not eat ordinary brackets", () => {
    expect(splitAnchorLinks("array[0] and (parens)")).toEqual([
      "array[0] and (parens)",
    ]);
  });

  it("is not confused by a previous call (no sticky lastIndex)", () => {
    const s = "[a](anchor:d?page=1)";
    expect(splitAnchorLinks(s)).toHaveLength(1);
    expect(splitAnchorLinks(s)).toHaveLength(1);
  });
});

describe("AnchoredText", () => {
  it("renders an anchor link as a clickable source ref", () => {
    const { container } = draw(
      "Rated head is [24 m](anchor:lkh?page=3&region=r2) at 8 m3/h.",
    );
    const link = container.querySelector('[data-testid="source-ref-link"]');
    expect(link?.textContent).toContain("24 m");
  });

  it("keeps the words around the link", () => {
    const { container } = draw("Head is [24 m](anchor:lkh?page=3) at duty.");
    expect(container.textContent).toContain("Head is");
    expect(container.textContent).toContain("at duty.");
  });

  it("renders plain prose unchanged", () => {
    const { container } = draw("no links here");
    expect(container.textContent).toBe("no links here");
    expect(container.querySelector('[data-testid="source-ref-link"]')).toBeNull();
  });

  it("does not format markdown, because that is what a markdown card is for", () => {
    const { container } = draw("**bold** stays literal");
    expect(container.textContent).toBe("**bold** stays literal");
    expect(container.querySelector("strong")).toBeNull();
  });

  it("shows a source preview after hovering a link, not before", async () => {
    // The delay is the point: sweeping a cursor across a paragraph of linked
    // values must not strobe a panel per link.
    const user = userEvent.setup();
    const { container } = draw("Head is [24 m](anchor:lkh?page=3&bbox=1,2,3,4) at duty.");
    const link = container.querySelector('[data-testid="source-ref-link"]')!;
    expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeNull();

    await user.hover(link);

    await waitFor(
      () => expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeTruthy(),
      { timeout: 2000 },
    );
  });

  it("takes the preview away again when the pointer leaves", async () => {
    const user = userEvent.setup();
    const { container } = draw("Head is [24 m](anchor:lkh?page=3&bbox=1,2,3,4) at duty.");
    const link = container.querySelector('[data-testid="source-ref-link"]')!;
    await user.hover(link);
    await waitFor(
      () => expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeTruthy(),
      { timeout: 2000 },
    );

    await user.unhover(link);
    await waitFor(
      () => expect(document.querySelector('[data-testid="ref-hover-preview"]')).toBeNull(),
      { timeout: 2000 },
    );
  });

  it("marks a ref that points nowhere", () => {
    const { container } = draw("[nowhere](anchor:?page=)");
    expect(container.querySelector('[data-testid="source-ref-broken"]')).toBeTruthy();
  });
});
