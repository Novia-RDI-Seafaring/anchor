import { describe, expect, it } from "vitest";

import { connectClick } from "./connect";

describe("connector tool clicks", () => {
  it("the first click picks where the connector starts", () => {
    expect(connectClick(null, "a")).toEqual({ type: "start", source: "a" });
  });

  it("the second click on another element draws the connector", () => {
    expect(connectClick("a", "b")).toEqual({ type: "create", source: "a", target: "b" });
  });

  it("clicking the same element again cancels", () => {
    expect(connectClick("a", "a")).toEqual({ type: "cancel" });
  });
});
