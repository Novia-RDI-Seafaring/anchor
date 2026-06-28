import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import { canvases, type WorkspaceListEntry } from "@/api/canvases";

import { refreshWorkspaces, useWorkspacesList } from "./useWorkspacesList";

vi.mock("@/api/canvases", () => ({
  canvases: {
    list: vi.fn(),
  },
}));

function workspace(slug: string): WorkspaceListEntry {
  return {
    slug,
    title: "",
    created_at: 0,
    node_count: 0,
    edge_count: 0,
    references: [],
    referenced_by: [],
  };
}

function Probe() {
  const snap = useWorkspacesList();
  return <div>{snap ? snap.items.map((it) => it.slug).join(",") : "loading"}</div>;
}

describe("useWorkspacesList", () => {
  it("updates subscribers when the shared workspace cache refreshes", async () => {
    vi.mocked(canvases.list)
      .mockResolvedValueOnce([workspace("parent")])
      .mockResolvedValueOnce([workspace("parent"), workspace("child")]);

    render(<Probe />);

    expect(await screen.findByText("parent")).toBeTruthy();

    await act(async () => {
      await refreshWorkspaces();
    });

    await waitFor(() => {
      expect(screen.getByText("parent,child")).toBeTruthy();
    });
  });
});
