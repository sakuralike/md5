import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";
import {
  changeAdminUserStatus,
  createAdminUser,
  listAdminUsers,
  reauthenticateAdmin,
  revokeAdminUserSessions,
} from "./users";

vi.mock("./api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);

describe("admin user service", () => {
  beforeEach(() => mockedApiRequest.mockClear());

  it("serializes governance filters with backend names", async () => {
    const response = await listAdminUsers(
      {
        status: "disabled",
        role: "trusted_contributor",
        query: "synthetic user",
        page: 2,
        pageSize: 10,
      },
      "synthetic-admin-token",
    );

    expect(response).toEqual({
      path: "/admin/users?status=disabled&role=trusted_contributor&query=synthetic+user&page=2&page_size=10",
    });
  });

  it("reauthenticates without persisting credentials in the service", async () => {
    await reauthenticateAdmin(
      { currentPassword: "SyntheticPass123!", totpCode: "123456" },
      "synthetic-admin-token",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/auth/reauthenticate",
      {
        method: "POST",
        body: JSON.stringify({
          current_password: "SyntheticPass123!",
          totp_code: "123456",
        }),
      },
      "synthetic-admin-token",
    );
  });

  it("sends status changes with an idempotency key and backend field names", async () => {
    await changeAdminUserStatus(
      "synthetic/user",
      {
        expectedStatus: "active",
        status: "disabled",
        reasonCode: "security_risk",
        reauthToken: "synthetic-reauth-token",
      },
      "synthetic-admin-token",
      "synthetic-idempotency-key-0001",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/users/synthetic%2Fuser/status",
      {
        method: "PATCH",
        headers: { "Idempotency-Key": "synthetic-idempotency-key-0001" },
        body: JSON.stringify({
          expected_status: "active",
          status: "disabled",
          reason_code: "security_risk",
          reauth_token: "synthetic-reauth-token",
        }),
      },
      "synthetic-admin-token",
    );
  });

  it("sends session revocation with optimistic concurrency state", async () => {
    await revokeAdminUserSessions(
      "synthetic-user-id",
      {
        expectedActiveSessionCount: 2,
        reasonCode: "incident_response",
        reauthToken: "synthetic-reauth-token",
      },
      "synthetic-admin-token",
      "synthetic-idempotency-key-0002",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/users/synthetic-user-id/sessions/revoke",
      {
        method: "POST",
        headers: { "Idempotency-Key": "synthetic-idempotency-key-0002" },
        body: JSON.stringify({
          expected_active_session_count: 2,
          reason_code: "incident_response",
          reauth_token: "synthetic-reauth-token",
        }),
      },
      "synthetic-admin-token",
    );
  });
  it("creates a user with an initial password only in the request body", async () => {
    await createAdminUser(
      {
        username: "manual_user",
        email: "manual-user@synthetic.example.com",
        password: "SyntheticManualCreate123!",
        role: "user",
        status: "active",
        email_verified: true,
      },
      "synthetic-admin-token",
    );

    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/users",
      {
        method: "POST",
        body: JSON.stringify({
          username: "manual_user",
          email: "manual-user@synthetic.example.com",
          password: "SyntheticManualCreate123!",
          role: "user",
          status: "active",
          email_verified: true,
        }),
      },
      "synthetic-admin-token",
    );
  });

});
