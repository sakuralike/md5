import { describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import { getMyReferralProfile } from "./referrals";

vi.mock("./api", () => ({
  apiRequest: vi.fn(() => Promise.resolve({})),
}));

describe("referral service", () => {
  it("loads the authenticated user's referral profile", async () => {
    await getMyReferralProfile("synthetic-access-token");
    expect(vi.mocked(apiRequest)).toHaveBeenCalledWith(
      "/referrals/me",
      {},
      "synthetic-access-token",
    );
  });
});
