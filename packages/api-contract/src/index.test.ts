import { describe, expect, it } from "vitest";
import {
  ApiError,
  isPrivilegedRole,
  THIRD_PARTY_API_V1_PATHS,
  THIRD_PARTY_API_V1_SCOPES,
<<<<<<< HEAD
=======
  THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS,
>>>>>>> d62e3c2523995be8cd5ce68eb67421fca37b2a2d
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
  it("publishes stable third-party desktop API v1 constants", () => {
    expect(THIRD_PARTY_API_V1_SCOPES).toEqual([
      "profile:read",
      "hash:read",
<<<<<<< HEAD
=======
      "announcements:read",
      "updates:read",
>>>>>>> d62e3c2523995be8cd5ce68eb67421fca37b2a2d
      "desktop:installations",
      "desktop:verification",
      "desktop:verification:trusted",
    ]);
<<<<<<< HEAD
=======
    expect(THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS.map((option) => option.value)).toEqual([
      "profile:read",
      "hash:read",
      "announcements:read",
      "updates:read",
      "desktop:installations",
      "desktop:verification",
    ]);
    expect(THIRD_PARTY_API_V1_PATHS.hashDetail).toBe(
      "/third-party/hashes/{algorithm}/{digest}",
    );
    expect(THIRD_PARTY_API_V1_PATHS.hashComments).toBe(
      "/third-party/hashes/{algorithm}/{digest}/comments",
    );
    expect(THIRD_PARTY_API_V1_PATHS.announcements).toBe("/third-party/announcements");
    expect(THIRD_PARTY_API_V1_PATHS.updatesCheck).toBe("/third-party/updates/check");
>>>>>>> d62e3c2523995be8cd5ce68eb67421fca37b2a2d
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
