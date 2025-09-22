import { describe, it, expect } from "vitest";
import { parseDialogue } from "../lib/parser";

describe("parseDialogue (stub)", () => {
  it("returns structure with arrays and no throw", () => {
    const out = parseDialogue("[A]: Hello\nInvalid line without colon");
    expect(Array.isArray(out.characters)).toBe(true);
    expect(Array.isArray(out.utterances)).toBe(true);
  });
});
