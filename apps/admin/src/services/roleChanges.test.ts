import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  approveRoleChangeRequest,
  createRoleChangeRequest,
  listRoleChangeRequests,
  rejectRoleChangeRequest,
} from "./roleChanges";

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("admin role change service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("lists requests with status filters", async () => {
    await listRoleChangeRequests({ status: "pending", page: 2, pageSize: 25 }, "synthetic-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/role-change-requests?status=pending&page=2&page_size=25",
      {},
      "synthetic-token",
    );
  });

  it("creates a request without putting the idempotency key in the body", async () => {
    await createRoleChangeRequest(
      "target/user",
      {
        expectedRole: "user",
        requestedRole: "trusted_contributor",
        reasonCode: "trust_promotion",
        reauthToken: "synthetic-reauth-token",
      },
      "synthetic-token",
      "role-create-1",
    );
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/users/target%2Fuser/role-change-requests",
      {
        method: "POST",
        headers: { "Idempotency-Key": "role-create-1" },
        body: JSON.stringify({
          expected_role: "user",
          requested_role: "trusted_contributor",
          reason_code: "trust_promotion",
          reauth_token: "synthetic-reauth-token",
        }),
      },
      "synthetic-token",
    );
  });

  it("uses separate approve and reject endpoints with optimistic status checks", async () => {
    await approveRoleChangeRequest(
      "request/1",
      { reasonCode: "verified", reauthToken: "synthetic-reauth-token" },
      "synthetic-token",
      "approve-1",
    );
    await rejectRoleChangeRequest(
      "request/1",
      {
        reasonCode: "policy_conflict",
        reauthToken: "synthetic-reauth-token",
        expectedStatus: "pending",
      },
      "synthetic-token",
      "reject-1",
    );
    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      1,
      "/admin/role-change-requests/request%2F1/approve",
      {
        method: "POST",
        headers: { "Idempotency-Key": "approve-1" },
        body: JSON.stringify({
          expected_status: "pending",
          reason_code: "verified",
          reauth_token: "synthetic-reauth-token",
        }),
      },
      "synthetic-token",
    );
    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      2,
      "/admin/role-change-requests/request%2F1/reject",
      {
        method: "POST",
        headers: { "Idempotency-Key": "reject-1" },
        body: JSON.stringify({
          expected_status: "pending",
          reason_code: "policy_conflict",
          reauth_token: "synthetic-reauth-token",
        }),
      },
      "synthetic-token",
    );
  });
});
