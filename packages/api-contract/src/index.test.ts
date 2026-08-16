import { describe, expect, it } from "vitest";
import type {
  CommunityDirectConversationCreateRequest,
  CommunityDirectConversationCreateResponse,
  CommunityDirectMessageResponse,
  CommunityDirectReadStateUpdateRequest,
} from "./index";
import {
  ApiError,
  COMMUNITY_SEARCH_MODES,
  COMMUNITY_SEARCH_RESULT_TYPES,
  isPrivilegedRole,
  THIRD_PARTY_API_V1_PATHS,
  THIRD_PARTY_API_V1_SCOPES,
  THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS,
  THIRD_PARTY_OAUTH_GRANT_TYPES,
  THIRD_PARTY_RECEIPT_CANONICAL_FIELDS,
} from "./index";

describe("shared API contract", () => {
  it("classifies privileged roles", () => {
    expect(isPrivilegedRole("user")).toBe(false);
    expect(isPrivilegedRole("moderator")).toBe(true);
    expect(isPrivilegedRole("admin")).toBe(true);
  });

  it("defines privacy-safe direct-message contract shapes", () => {
    const create: CommunityDirectConversationCreateRequest = {
      recipient_username: "synthetic_receiver",
    };
    const message: CommunityDirectMessageResponse = {
      id: "message-1",
      conversation_id: "conversation-1",
      sender_username: "synthetic_sender",
      body: "仅用于契约测试的合成正文",
      sequence: 1,
      created_at: "2026-08-16T00:00:00Z",
    };
    const readState: CommunityDirectReadStateUpdateRequest = {
      last_read_sequence: 1,
    };
    const created: CommunityDirectConversationCreateResponse = {
      created: true,
      conversation: {
        id: "conversation-1",
        counterpart_username: create.recipient_username,
        counterpart_display_name: "Synthetic Receiver",
        counterpart_avatar_seed: "synthetic-seed",
        counterpart_avatar_url: null,
        last_message_at: "2026-08-16T00:00:00Z",
        unread_count: 1,
        last_read_sequence: 0,
        archived_at: null,
        muted_until: null,
        created_at: "2026-08-16T00:00:00Z",
        updated_at: "2026-08-16T00:00:00Z",
      },
    };

    expect(message.sequence).toBe(readState.last_read_sequence);
    expect(created.conversation.counterpart_username).toBe("synthetic_receiver");
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
      "announcements:read",
      "updates:read",
      "desktop:installations",
      "desktop:verification",
      "desktop:verification:trusted",
    ]);
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
