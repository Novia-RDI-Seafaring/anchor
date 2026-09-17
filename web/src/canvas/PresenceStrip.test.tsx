/**
 * PresenceStrip tests — the "who is on this canvas" chips.
 *
 * Pins the trust signal this exists for (#322 follow-up, part of #321):
 * an agent that is actively writing shows up as its own chip, so a human
 * watching nodes move knows who is moving them. Also pins that the strip
 * stays out of the way when it has nothing to say (empty roster) and that
 * the viewer's own entry reads as confirmation rather than news.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import type { PresenceEntry } from "@/realtime/sseClient";
import { useCanvasStore } from "@/stores/canvasStore";

import { PresenceStrip } from "./PresenceStrip";

const viewer: PresenceEntry = {
  client_id: "c1",
  kind: "human",
  label: "browser",
  connected_at: 1000,
  via: "sse",
};
const monitor: PresenceEntry = {
  client_id: "c2",
  kind: "human",
  label: "monitor",
  connected_at: 1005,
  via: "sse",
};
const agent: PresenceEntry = {
  kind: "agent",
  label: "claude-code",
  connected_at: 1010,
  last_write_at: 1020,
  via: "writes",
};

function seed(present: PresenceEntry[], you: string | null = null) {
  useCanvasStore.setState({ presence: present, presenceSelfId: you });
}

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe("PresenceStrip", () => {
  it("renders nothing while the roster is empty", () => {
    seed([]);
    const { container } = render(<PresenceStrip />);
    expect(container.innerHTML).toBe("");
  });

  it("lists every viewer and actively-writing agent", () => {
    seed([viewer, monitor, agent]);
    render(<PresenceStrip />);
    expect(screen.getByText("monitor")).toBeTruthy();
    expect(screen.getByText("claude-code")).toBeTruthy();
    // A writing agent says so on hover — that is the explanation for
    // nodes appearing on their own.
    expect(screen.getByTitle("claude-code — agent, actively writing")).toBeTruthy();
    expect(screen.getByTitle("monitor — viewing live")).toBeTruthy();
  });

  it("marks the viewer's own entry and leaves the others alone", () => {
    seed([viewer, monitor], "c1");
    render(<PresenceStrip />);
    expect(screen.getByText("browser (you)")).toBeTruthy();
    expect(screen.getByTitle("browser (you)")).toBeTruthy();
    expect(screen.getByText("monitor")).toBeTruthy();
  });

  it("falls back to the actor kind when an entry has no label", () => {
    seed([{ kind: "agent", connected_at: 1, via: "writes", label: null }]);
    render(<PresenceStrip />);
    expect(screen.getByText("agent")).toBeTruthy();
  });
});
