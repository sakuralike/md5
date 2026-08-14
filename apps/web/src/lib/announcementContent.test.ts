import { describe, expect, it } from "vitest";
import { announcementAutoCloseMilliseconds } from "./announcementContent";


describe("announcementAutoCloseMilliseconds", () => {
  it("converts configured seconds and disables invalid values", () => {
    expect(announcementAutoCloseMilliseconds(15)).toBe(15_000);
    expect(announcementAutoCloseMilliseconds(null)).toBeNull();
    expect(announcementAutoCloseMilliseconds(0)).toBeNull();
    expect(announcementAutoCloseMilliseconds(86_401)).toBeNull();
  });
});
