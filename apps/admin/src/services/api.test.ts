import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@password-detective/api-contract";
import { apiRequest } from "./api";

describe("admin apiRequest", () => {
  afterEach(() => vi.unstubAllGlobals());

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
    expect(headers.get("X-Request-ID")).toBe("admin_synthetic-request-id");
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
