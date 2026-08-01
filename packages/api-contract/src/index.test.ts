import { describe, expect, it } from "vitest";
import { ApiError, isPrivilegedRole } from "./index";

describe("shared API contract", () => {
  it("classifies privileged roles", () => {
    expect(isPrivilegedRole("user")).toBe(false);
    expect(isPrivilegedRole("moderator")).toBe(true);
    expect(isPrivilegedRole("admin")).toBe(true);
  });

  it("preserves standard API error metadata", () => {
    const error = new ApiError(401, {
      code: "auth.authentication_required",
      message: "需要登录",
      details: {},
      request_id: "req_test",
    });
    expect(error.message).toBe("需要登录");
    expect(error.body.request_id).toBe("req_test");
  });
});
