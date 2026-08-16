import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import { getCommunitySearchHealth } from "./communitySearch";

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("community search health service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("requests only the aggregate search-health endpoint", async () => {
    await getCommunitySearchHealth("synthetic-admin-token");

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/community/search/health",
      {},
      "synthetic-admin-token",
    );
  });
});
