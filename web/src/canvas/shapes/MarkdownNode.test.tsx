/**
 * MarkdownNode — a card whose body renders as rich text.
 */
import { act, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useUiStore } from "@/stores/uiStore";

import { MarkdownNode } from "./MarkdownNode";

function renderMarkdown(data: Record<string, unknown>, selected = false) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <MarkdownNode
                {...({
                  id: "m1",
                  data,
                  selected,
                  dragging: false,
                  isConnectable: false,
                  positionAbsoluteX: 0,
                  positionAbsoluteY: 0,
                  type: "markdown",
                  zIndex: 0,
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                } as any)}
              />
            </ReactFlowProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MarkdownNode", () => {
  it("renders headings, emphasis and lists as elements, not as asterisks", () => {
    const { container, getByText } = renderMarkdown({
      text: "## Findings\n\nThe seal is **worn**.\n\n- first\n- second",
    });
    expect(container.querySelector("h2")?.textContent).toBe("Findings");
    expect(container.querySelector("strong")?.textContent).toBe("worn");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    // The source syntax is gone from the visible text.
    expect(container.textContent).not.toContain("**");
    expect(getByText("first")).toBeTruthy();
  });

  it("renders a GitHub-flavoured table", () => {
    const { container } = renderMarkdown({
      text: "| Option | Cost |\n| --- | --- |\n| A | 3 |\n| B | 5 |",
    });
    expect(container.querySelectorAll("th")).toHaveLength(2);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
  });

  it("renders a fenced code block verbatim", () => {
    const { container } = renderMarkdown({ text: "```\nk = 3 * x\n```" });
    const pre = container.querySelector("pre");
    expect(pre?.textContent).toContain("k = 3 * x");
  });

  it("escapes raw HTML in the source instead of rendering it", () => {
    // Markdown reaches this card from agents as well as people, so a
    // <script> or an onerror image in the source must stay inert text.
    const { container } = renderMarkdown({
      text: 'Hello <img src="x" onerror="alert(1)"> <b>bold?</b>',
    });
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>bold?</b>");
  });

  it("opens links in a new tab without leaking the opener", () => {
    const { container } = renderMarkdown({ text: "[docs](https://example.com)" });
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("https://example.com");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toContain("noopener");
  });

  it("keeps a javascript: link from becoming a live href", () => {
    const { container } = renderMarkdown({ text: "[click](javascript:alert(1))" });
    expect(container.querySelector("a")?.getAttribute("href")).not.toContain("javascript:");
  });

  it("renders an anchor: link as a source ref, not as a web link", () => {
    const { container } = renderMarkdown({
      text: "Rated head is [24 m](anchor:lkh-5?page=3&region=r2).",
    });
    const ref = container.querySelector("[data-testid='source-ref-link']");
    expect(ref).toBeTruthy();
    expect(ref?.textContent).toContain("24 m");
    // It opens a document in the viewer; it is not a navigable href.
    expect(container.querySelector("a")).toBeNull();
    expect(ref?.getAttribute("title")).toContain("page 3");
    expect(ref?.getAttribute("title")).toContain("region r2");
  });

  it("shows a source ref that points nowhere as broken", () => {
    const { container } = renderMarkdown({ text: "Head is [24 m](anchor:lkh-5) here." });
    const broken = container.querySelector("[data-testid='source-ref-broken']");
    expect(broken).toBeTruthy();
    expect(broken?.className).toContain("line-through");
    expect(container.querySelector("[data-testid='source-ref-link']")).toBeNull();
  });

  it("still blocks a javascript: link while allowing anchor:", () => {
    // Widening the URL allowlist by one scheme must not widen it by two.
    const { container } = renderMarkdown({
      text: "[a](javascript:alert(1)) and [b](anchor:d?page=1)",
    });
    expect(container.querySelector("a")?.getAttribute("href")).not.toContain("javascript:");
    expect(container.querySelector("[data-testid='source-ref-link']")).toBeTruthy();
  });

  it("hides the title strip until the card is named or selected", () => {
    const { container: plain } = renderMarkdown({ text: "body" });
    expect(plain.textContent).not.toContain("untitled");
    const { container: chosen } = renderMarkdown({ text: "body" }, true);
    expect(chosen.textContent).toContain("untitled");
    const { container: named } = renderMarkdown({ label: "Notes", text: "body" });
    expect(named.textContent).toContain("Notes");
  });

  it("invites the first Markdown when the body is empty and the card is selected", () => {
    const { getByText } = renderMarkdown({}, true);
    expect(getByText("double-click to write Markdown")).toBeTruthy();
  });

  it("puts the caret in the body of a freshly placed card, not in its title", async () => {
    // Both editors live on this card. The title is optional, so the body
    // claims the pending-focus stamp — place one and type Markdown.
    useUiStore.setState({ pendingInlineRenameNodeId: "m1" });
    const { container } = renderMarkdown({}, true);
    await act(async () => {});
    expect(container.querySelector("textarea")).toBeTruthy();
    expect(container.querySelector("input")).toBeNull();
  });

  it("edits the Markdown source in a textarea, where Enter breaks the line", async () => {
    const user = userEvent.setup();
    const { container, getByText } = renderMarkdown({ text: "one" }, true);
    await user.dblClick(getByText("one"));
    const area = container.querySelector("textarea");
    expect(area).toBeTruthy();
    expect(area?.value).toBe("one");
    await user.type(area!, "{Enter}two");
    // Enter inserted a newline instead of committing and closing the editor.
    expect(container.querySelector("textarea")?.value).toBe("one\ntwo");
  });
});
