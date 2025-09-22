import { describe, it, expect } from "vitest";
import { generate, getStatus, downloadResult } from "../api/client";

describe("api client", () => {
  it("exports functions", () => {
    expect(typeof generate).toBe("function");
    expect(typeof getStatus).toBe("function");
    expect(typeof downloadResult).toBe("function");
  });
});
