/**
 * NodeContextMenu "Ask agent…" (#344): the context-menu entry arms the
 * ask composer for the effective selection and closes the menu.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useThreadsStore } from "@/threads/threadsStore";

import { NodeContextMenu } from "./NodeContextMenu";

vi.mock("@/api/canvases", () => ({ canvases: {} }));

beforeEach(() => {
  useThreadsStore.setState({ composerNodeIds: null });
});

describe("NodeContextMenu ask entry", () => {
  it("opens the composer for the multi-selection", () => {
    const onClose = vi.fn();
    render(
      <NodeContextMenu
        workspaceSlug="plant"
        target={{ x: 10, y: 10, nodeId: "n1", selectedIds: ["n1", "n2"], hasEdges: false }}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId("context-ask-agent"));
    expect(useThreadsStore.getState().composerNodeIds).toEqual(["n1", "n2"]);
    expect(onClose).toHaveBeenCalled();
  });

  it("falls back to the right-clicked node when nothing else is selected", () => {
    render(
      <NodeContextMenu
        workspaceSlug="plant"
        target={{ x: 10, y: 10, nodeId: "n1", selectedIds: [], hasEdges: false }}
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("context-ask-agent"));
    expect(useThreadsStore.getState().composerNodeIds).toEqual(["n1"]);
  });
});
