import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import { getPopupAnnouncements } from "./announcements";

vi.mock("./api", () => ({ apiRequest: vi.fn() }));

const mockedApiRequest = vi.mocked(apiRequest);

describe("popup announcement service", () => {
  beforeEach(() => {
    mockedApiRequest.mockReset();
    vi.spyOn(Date, "now").mockReturnValue(1_786_659_200_000);
  });

  it("requests current published announcements without browser cache", async () => {
    mockedApiRequest.mockResolvedValue({ items: [] });

    await getPopupAnnouncements(99);

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/web/announcements?limit=20&refresh=1786659200000",
      { cache: "no-store" },
    );
  });
});
