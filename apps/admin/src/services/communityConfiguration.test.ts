import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import { createCommunityBoard, listCommunityBoards, updateCommunityBoard } from "./communityConfiguration";

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);
const createPayload = {
  code: "synthetic_lab",
  name: "合成研究",
  description: "仅用于合成数据讨论。",
  sort_order: 50,
  minimum_role: "trusted_contributor" as const,
  is_read_only: false,
  status: "active" as const,
};

describe("community configuration service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("lists all boards through the admin-only endpoint", async () => {
    await listCommunityBoards("synthetic-admin-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/community/boards",
      {},
      "synthetic-admin-token",
    );
  });

  it("creates and updates boards with idempotency keys", async () => {
    await createCommunityBoard(createPayload, "synthetic-admin-token", "synthetic-create-key");
    await updateCommunityBoard(
      "synthetic/lab",
      { ...createPayload, is_read_only: true },
      "synthetic-admin-token",
      "synthetic-update-key",
    );

    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      1,
      "/admin/community/boards",
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": "synthetic-create-key" },
      }),
      "synthetic-admin-token",
    );
    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      2,
      "/admin/community/boards/synthetic%2Flab",
      expect.objectContaining({
        method: "PATCH",
        headers: { "Idempotency-Key": "synthetic-update-key" },
      }),
      "synthetic-admin-token",
    );
  });
});
