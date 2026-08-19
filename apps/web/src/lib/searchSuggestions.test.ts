import { describe, expect, it } from "vitest";
import { getPublicSearchSuggestions, isDisallowedSuggestionQuery } from "./searchSuggestions";

describe("public search suggestions", () => {
  it("only returns reviewed public vocabulary", () => {
    expect(getPublicSearchSuggestions("sha").map((item) => item.value)).toEqual([
      "SHA-1",
      "SHA-256",
      "SHA-512",
    ]);
    expect(getPublicSearchSuggestions("社区").some((item) => item.kind === "navigation")).toBe(true);
  });

  it("does not suggest from hashes, passwords, paths, or private-looking queries", () => {
    expect(getPublicSearchSuggestions("a".repeat(32))).toEqual([]);
    expect(getPublicSearchSuggestions("密码")).toEqual([]);
    expect(getPublicSearchSuggestions("C:\\archive.zip")).toEqual([]);
    expect(isDisallowedSuggestionQuery("candidate-password")).toBe(true);
  });
});
