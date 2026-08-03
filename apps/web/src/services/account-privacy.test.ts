import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cancelAccountDeletion,
  confirmAuthorizationDeclaration,
  reauthenticate,
  requestAccountDeletion,
  requestPrivacyExport,
} from "./account";

describe("account privacy service", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubJsonResponse(body: object = {}) {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-privacy-operation-key" });
    return fetchMock;
  }

  it("confirms a versioned authorization declaration with idempotency", async () => {
    const fetchMock = stubJsonResponse({ id: "declaration-1" });
    const payload = { purpose: "privacy_export", source: "web", accepted: true } as const;

    await confirmAuthorizationDeclaration("access-token", payload);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toBe("/api/v1/me/authorization-declarations");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify(payload));
    expect(headers.get("Idempotency-Key")).toBe("synthetic-privacy-operation-key");
  });

  it("creates export and deletion state-machine requests", async () => {
    const fetchMock = stubJsonResponse({ id: "request-1" });

    await requestPrivacyExport("access-token");
    await reauthenticate("access-token", {
      purpose: "account_deletion",
      current_password: "SyntheticPrivacyPass123!",
      totp_code: "123456",
    });
    await requestAccountDeletion("access-token", {
      reauth_token: "reauth_synthetic-token-value-000000000000",
    });
    await cancelAccountDeletion("access-token", "request-1");

    const requests = fetchMock.mock.calls as [string, RequestInit][];
    expect(requests.map(([url]) => url)).toEqual([
      "/api/v1/me/privacy/exports",
      "/api/v1/me/security/reauthenticate",
      "/api/v1/me/privacy/deletion-requests",
      "/api/v1/me/privacy/deletion-requests/request-1/cancel",
    ]);
    expect(requests.every(([, init]) => init.method === "POST")).toBe(true);
    expect((requests[1][1].headers as Headers).get("Idempotency-Key")).toBeNull();
  });
});
