import { describe, expect, it } from "vitest";
import {
  ApiError,
  COMMUNITY_SEARCH_MODES,
  COMMUNITY_SEARCH_RESULT_TYPES,
  isPrivilegedRole,
  THIRD_PARTY_API_V1_PATHS,
  THIRD_PARTY_API_V1_SCOPES,
  THIRD_PARTY_OAUTH_GRANT_TYPES,
  THIRD_PARTY_RECEIPT_CANONICAL_FIELDS,
} from "./index";

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

  it("publishes stable community search capability constants", () => {
    expect(COMMUNITY_SEARCH_RESULT_TYPES).toEqual([
      "post",
      "user",
      "board",
      "group",
    ]);
    expect(COMMUNITY_SEARCH_MODES).toEqual([
      "ngram",
      "prefix_fallback",
      "test",
    ]);
  });

  it("publishes stable third-party desktop API v1 constants", () => {
    expect(THIRD_PARTY_API_V1_SCOPES).toEqual([
      "profile:read",
      "hash:read",
      "desktop:installations",
      "desktop:verification",
      "desktop:verification:trusted",
    ]);
    expect(THIRD_PARTY_OAUTH_GRANT_TYPES).toEqual([
      "authorization_code",
      "refresh_token",
    ]);
    expect(THIRD_PARTY_API_V1_PATHS.oauthToken).toBe("/third-party/oauth/token");
    expect(THIRD_PARTY_API_V1_PATHS.verificationReceipts).toBe(
      "/third-party/verification-receipts",
    );
    expect(THIRD_PARTY_RECEIPT_CANONICAL_FIELDS).toEqual([
      "version",
      "client_id",
      "challenge_id",
      "challenge_nonce",
      "installation_id",
      "account_id",
      "candidate_id",
      "fingerprint_algorithm",
      "fingerprint_digest",
      "candidate_digest",
      "outcome",
      "archive_format",
      "client_version",
      "verified_at",
    ]);
  });
});
