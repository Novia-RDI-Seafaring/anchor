import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { agentReach, readerName } from "./reach";
import { SentStatus } from "./SentStatus";

const sent = { id: "i1", payload: {}, status: "pending", created_at: 1000 };

describe("agentReach", () => {
  it("is waiting while the remark is fresh", () => {
    expect(agentReach(sent, 1010_000).kind).toBe("waiting");
  });
  it("says nobody has read it once the wait is long", () => {
    expect(agentReach(sent, 1031_000).kind).toBe("unheard");
  });
  it("names who saw it and when", () => {
    const seen = { ...sent, seen_at: 1005, seen_by: { kind: "agent", label: "claude-code" } };
    expect(agentReach(seen, 1005_000 + 125_000)).toEqual({ kind: "seen", by: "claude-code", ago: "2 min ago" });
  });
  it("words a reader without a name", () => {
    expect(readerName({ kind: "agent" })).toBe("an agent");
    expect(readerName({ kind: "human", label: "cli" })).toBe("the CLI");
  });
});

describe("SentStatus", () => {
  const hint = { prompt: "Check the inbox.", command: "anchor intents" };
  it("offers what to do when no agent has read it", () => {
    vi.spyOn(Date, "now").mockReturnValue(1100_000);
    render(<SentStatus intent={sent} hint={hint} onWithdraw={() => {}} />);
    expect(screen.getByTestId("comment-lasso-reach").dataset.reach).toBe("unheard");
    expect(screen.queryByTestId("comment-lasso-reach-hint")).toBeNull();
    fireEvent.click(screen.getByTestId("comment-lasso-reach-how"));
    expect(screen.getByTestId("comment-lasso-reach-hint").textContent).toContain("Check the inbox.");
    expect(screen.getByTestId("comment-lasso-reach-hint").textContent).toContain("anchor intents");
    vi.restoreAllMocks();
  });
  it("shows who saw it, with no hint", () => {
    vi.spyOn(Date, "now").mockReturnValue(1100_000);
    render(
      <SentStatus
        intent={{ ...sent, seen_at: 1010, seen_by: { kind: "agent", label: "claude-code" } }}
        hint={hint}
        onWithdraw={() => {}}
      />,
    );
    expect(screen.getByTestId("comment-lasso-reach").textContent).toContain("seen by claude-code");
    expect(screen.queryByTestId("comment-lasso-reach-how")).toBeNull();
    vi.restoreAllMocks();
  });
});
