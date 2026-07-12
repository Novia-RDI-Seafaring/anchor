import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { runtimeStatus } from "@/api/status";

import { ExtensionStatusPanel } from "./ExtensionStatusPanel";

vi.mock("@/api/status", () => ({
  runtimeStatus: { getExtensions: vi.fn() },
}));

describe("ExtensionStatusPanel", () => {
  it("renders normalized availability and refreshes on demand", async () => {
    vi.mocked(runtimeStatus.getExtensions).mockResolvedValue({
      extensions: [
        {
          name: "anchor-cad",
          source: "bundled",
          available: true,
          reason: null,
          error_type: null,
        },
        {
          name: "anchor-fmus",
          source: "bundled",
          available: false,
          reason: "FMPy is not installed",
          error_type: "FmuRuntimeUnavailableError",
        },
      ],
      summary: { available: 1, unavailable: 1 },
    });

    render(<ExtensionStatusPanel />);

    expect(await screen.findByText("1 available, 1 unavailable")).toBeTruthy();
    expect(screen.getByText("anchor-cad")).toBeTruthy();
    expect(screen.getByText("FMPy is not installed")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Refresh extension status" }));
    await waitFor(() => expect(runtimeStatus.getExtensions).toHaveBeenCalledTimes(2));
  });

  it("shows a stable error state when diagnostics cannot be loaded", async () => {
    vi.mocked(runtimeStatus.getExtensions).mockRejectedValue(new Error("offline"));

    render(<ExtensionStatusPanel />);

    expect(await screen.findByText("Runtime status unavailable")).toBeTruthy();
  });
});
