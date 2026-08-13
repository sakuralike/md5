import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@password-detective/api-contract";
import { apiRequest, setAccessTokenRefreshHandler } from "./api";

describe("web apiRequest", () => {
  afterEach(() => {
    setAccessTokenRefreshHandler(null);
    vi.unstubAllGlobals();
  });

  it("adds request and authorization headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    await expect(apiRequest("/health/live", {}, "access-token")).resolves.toEqual({
      status: "ok",
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer access-token");
    expect(headers.get("X-Request-ID")).toBe("web_synthetic-request-id");
  });

  it("refreshes an expired access token and retries the protected request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            code: "auth.access_token_expired",
            message: "访问令牌已过期",
            details: {},
            request_id: "req_expired",
          }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });
    setAccessTokenRefreshHandler(vi.fn().mockResolvedValue("refreshed-access-token"));

    await expect(apiRequest("/me/profile", {}, "expired-access-token")).resolves.toEqual({
      status: "ok",
    });

    const retryHeaders = (fetchMock.mock.calls[1]?.[1] as RequestInit).headers as Headers;
    expect(retryHeaders.get("Authorization")).toBe("Bearer refreshed-access-token");
  });

  it("throws the standardized API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "auth.session_revoked",
            message: "登录会话已失效",
            details: {},
            request_id: "req_synthetic",
          }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    vi.stubGlobal("crypto", { randomUUID: () => "synthetic-request-id" });

    const caught = await apiRequest("/me/profile").catch((error: unknown) => error);
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).body.code).toBe("auth.session_revoked");
  });
});
