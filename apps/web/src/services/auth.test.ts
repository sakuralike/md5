import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loginBrowser,
  requestPasswordReset,
  resendEmailVerification,
  resetPassword,
  verifyEmail,
} from "./auth";

describe("public account recovery service", () => {
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
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-recovery-key" });
    return fetchMock;
  }

  it("submits optional TOTP during browser login", async () => {
    const fetchMock = stubJsonResponse({
      access_token: "synthetic-access-token",
      token_type: "bearer",
      expires_in: 900,
      mfa_verified: true,
      user: { id: "usr_synthetic" },
    });

    await loginBrowser({
      login: "synthetic_detective",
      password: "SyntheticPass123!",
      totp_code: "123456",
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/web/auth/login");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(
      JSON.stringify({
        login: "synthetic_detective",
        password: "SyntheticPass123!",
        totp_code: "123456",
      }),
    );
  });

  it("uses an idempotency key without changing the anti-enumeration request", async () => {
    const fetchMock = stubJsonResponse();

    await requestPasswordReset({ email: "synthetic@example.com" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toBe("/api/v1/auth/password/forgot");
    expect(headers.get("Idempotency-Key")).toBe("synthetic-recovery-key");
    expect(init.body).toBe(JSON.stringify({ email: "synthetic@example.com" }));
  });

  it("keeps verification and reset tokens in request bodies only", async () => {
    const fetchMock = stubJsonResponse();

    await verifyEmail({ token: "synthetic-verification-token-0001" });
    await resetPassword({
      token: "synthetic-password-reset-token-0001",
      new_password: "SyntheticNext456!",
    });

    const requests = fetchMock.mock.calls as [string, RequestInit][];
    expect(requests[0][0]).toBe("/api/v1/auth/email/verify");
    expect(requests[0][1].body).toBe(
      JSON.stringify({ token: "synthetic-verification-token-0001" }),
    );
    expect(requests[1][0]).toBe("/api/v1/auth/password/reset");
    expect(requests[1][1].body).toBe(
      JSON.stringify({
        token: "synthetic-password-reset-token-0001",
        new_password: "SyntheticNext456!",
      }),
    );
  });

  it("authorizes verification-email resend with the current session", async () => {
    const fetchMock = stubJsonResponse();

    await resendEmailVerification("synthetic-access-token");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(url).toBe("/api/v1/auth/email/resend");
    expect(headers.get("Authorization")).toBe("Bearer synthetic-access-token");
  });
});
