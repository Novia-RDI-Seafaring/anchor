/**
 * IngestActivityPill.test — the project-level ingestion-activity pill (#51).
 *
 * Covers the load-bearing behaviour:
 *   1. Renders nothing when nothing is ingesting (graceful at zero).
 *   2. Shows "N ingesting" for the running count.
 *   3. Expands to a per-doc list with stage label + a progress bar.
 *   4. Surfaces the failed stage for a failed ingest.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { IngestActivity } from "@/realtime/ingestsSse";

import { IngestActivityPillView } from "./IngestActivityPill";

function act(over: Partial<IngestActivity> = {}): IngestActivity {
  return {
    slug: "pump",
    filename: "pump.pdf",
    stage: "gold_regions",
    current: 2,
    total: 4,
    status: "running",
    started_at: 1,
    updated_at: 2,
    pct: 50,
    ...over,
  };
}

describe("IngestActivityPillView", () => {
  it("renders nothing when there is no activity", () => {
    const { container } = render(<IngestActivityPillView ingests={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the running count", () => {
    render(
      <IngestActivityPillView
        ingests={[act({ slug: "a" }), act({ slug: "b" })]}
      />,
    );
    expect(screen.getByText("2 ingesting")).toBeTruthy();
  });

  it("expands to a per-doc list with stage + progress bar", () => {
    render(<IngestActivityPillView ingests={[act({ slug: "pump", filename: "pump.pdf" })]} />);
    // Collapsed: no list yet.
    expect(screen.queryByText("pump.pdf")).toBeNull();
    fireEvent.click(screen.getByText("1 ingesting"));
    // Expanded: filename + stage label + a progress bar at the pct width.
    expect(screen.getByText("pump.pdf")).toBeTruthy();
    expect(screen.getByText("extracting regions")).toBeTruthy();
    const bar = screen.getByTestId("bar-pump") as HTMLElement;
    expect(bar.style.width).toBe("50%");
  });

  it("surfaces the failed stage for a failed ingest", () => {
    render(
      <IngestActivityPillView
        ingests={[act({ slug: "boom", status: "failed", stage: "silver_extract" })]}
      />,
    );
    // Zero running but a failure present -> the pill still shows.
    fireEvent.click(screen.getByText("1 failed"));
    expect(screen.getByText("failed: extracting")).toBeTruthy();
  });
});
