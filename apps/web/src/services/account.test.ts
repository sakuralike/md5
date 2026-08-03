import { afterEach, describe, expect, it, vi } from "vitest";
import {
  beginTotpSetup,
  changePassword,
  confirmTotp,
  disableTotp,
  reauthenticate,
  updateProfile,
} from "./account";

describe("account security service", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubJsonResponse(body: object = { message: "ok" }) {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-operation-key" });
    return fetchMock;
  }

  it("updates profile with authorization and idempotency", async () => {
    const fetchMock = stubJsonResponse({ username: "detective_updated" });

    await updateProfile("access-token", { username: "detective_updated" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toBe("/api/v1/me/profile");
    expect(init.method).toBe("PATCH");
    expect(init.body).toBe(JSON.stringify({ username: "detective_updated" }));
    expect(headers.get("Authorization")).toBe("Bearer access-token");
    expect(headers.get("Idempotency-Key")).toBe("synthetic-operation-key");
  });

  it("reauthenticates before sending a password change", async () => {
    const fetchMock = stubJsonResponse({
      reauth_token: "reauth_synthetic-token-value-000000000000",
      purpose: "password_change",
      expires_at: "2026-08-03T12:00:00Z",
    });
    const reauthPayload = {
      purpose: "password_change",
      current_password: "SyntheticPass123!",
      totp_code: "123456",
    } as const;
    const passwordPayload = {
      reauth_token: "reauth_synthetic-token-value-000000000000",
      new_password: "SyntheticNext456!",
    };

    await reauthenticate("access-token", reauthPayload);
    await changePassword("access-token", passwordPayload);

    const requests = fetchMock.mock.calls as [string, RequestInit][];
    expect(requests.map(([url]) => url)).toEqual([
      "/api/v1/me/security/reauthenticate",
      "/api/v1/me/security/password/change",
    ]);
    expect(requests[0][1].body).toBe(JSON.stringify(reauthPayload));
    expect(requests[1][1].body).toBe(JSON.stringify(passwordPayload));
  });

  it("uses separate TOTP setup, confirm and disable operations", async () => {
    const fetchMock = stubJsonResponse({
      secret: "SYNTHETICSECRET",
      provisioning_uri: "otpauth://totp/synthetic",
      message: "ok",
    });

    await beginTotpSetup("access-token");
    await confirmTotp("access-token", { code: "123456" });
    await disableTotp("access-token", {
      reauth_token: "reauth_synthetic-token-value-000000000000",
    });

    const requests = fetchMock.mock.calls as [string, RequestInit][];
    expect(requests.map(([url]) => url)).toEqual([
      "/api/v1/me/security/totp/setup",
      "/api/v1/me/security/totp/confirm",
      "/api/v1/me/security/totp",
    ]);
    expect(requests[0][1].method).toBe("POST");
    expect(requests[1][1].method).toBe("POST");
    expect(requests[2][1].method).toBe("DELETE");
  });
});
