import { describe, expect, it } from "vitest";
import type {
  CommunityDirectConversationCreateRequest,
  CommunityDirectConversationCreateResponse,
  CommunityDirectMessageCreatedEvent,
  CommunityDirectMessageListResponse,
  CommunityDirectMessageResponse,
  CommunityDirectReadStateUpdateRequest,
  CommunityDirectStreamReadyEvent,
  CommunityDirectUnreadChangedEvent,
  DesktopPluginCatalogResponse,
  DesktopPluginRevocationListResponse,
  HomeDiscoveryResponse,
  PublicSiteConfig,
} from "./index";
import {
  ApiError,
  COMMUNITY_SEARCH_MODES,
  COMMUNITY_SEARCH_RESULT_TYPES,
  DESKTOP_PLUGIN_ARCHITECTURES,
  DESKTOP_PLUGIN_PATHS,
  DESKTOP_PLUGIN_VERSION_STATUSES,
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

  it("exports direct-message stream snapshots and domain events", () => {
    const list: CommunityDirectMessageListResponse = {
      items: [],
      next_cursor: null,
      has_more: false,
      last_read_sequence: 2,
      counterpart_last_read_sequence: 3,
      unread_count: 1,
    };
    const ready: CommunityDirectStreamReadyEvent = {
      type: "ready",
      eventId: 8,
      totalUnreadCount: 1,
      resetRequired: false,
    };
    const created: CommunityDirectMessageCreatedEvent = {
      type: "message.created",
      eventId: 9,
      conversationId: "conversation-1",
      messageId: "message-2",
      messageSequence: 4,
      senderId: "user-1",
      createdAt: "2026-08-16T00:00:00Z",
    };
    const unread: CommunityDirectUnreadChangedEvent = {
      type: "unread.changed",
      eventId: 10,
      conversationId: "conversation-1",
      conversationUnreadCount: 0,
      totalUnreadCount: 0,
      changedAt: "2026-08-16T00:00:01Z",
    };

    expect(list.counterpart_last_read_sequence).toBe(3);
    expect([ready.eventId, created.eventId, unread.eventId]).toEqual([8, 9, 10]);
    expect(JSON.stringify(created)).not.toContain("body");
  });

  it("exports public site configuration and home discovery response shapes", () => {
    const config: PublicSiteConfig = {
      site_name: "合成侦探站",
      site_logo_url: "/brand/logo.svg",
      navigation: [{ label: "首页", path: "/", enabled: true, requires_auth: false }],
      seo: {
        enabled: true,
        indexing_enabled: false,
        home_title: "",
        keywords: [],
        description: "",
        title_separator: "-",
        default_image_url: "",
        open_graph_enabled: true,
      },
      legal: {
        icp_record: "合成 ICP 备 00000000 号",
        public_security_record: "",
        copyright_text: "2026 合成侦探站",
        public_contact_email: "contact@synthetic.example.com",
      },
      maintenance: {
        active: false,
        message: "系统正在维护，请稍后再试。",
      },
      registration: {
        mode: "open",
      },
    };
    const discovery: HomeDiscoveryResponse = {
      hot_hashes: [
        {
          algorithm: "sha256",
          digest: "a".repeat(64),
          like_count: 2,
          comment_count: 1,
          useful_vote_count: 3,
          heat_score: 12,
        },
      ],
      contribution_leaders: [{ rank: 1, uid: "user-1", username: "synthetic_user", score: 8 }],
      points_leaders: [{ rank: 1, uid: "user-2", username: "synthetic_points", score: 10 }],
    };

    expect(config.navigation[0]?.path).toBe("/");
    expect(config.maintenance.active).toBe(false);
    expect(discovery.hot_hashes[0]?.algorithm).toBe("sha256");
    expect(discovery.points_leaders[0]?.score).toBe(10);
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

  it("publishes desktop plugin control-plane paths and response shapes", () => {
    const catalog: DesktopPluginCatalogResponse = {
      items: [
        {
          slug: "com.synthetic.plugin",
          name: "Synthetic Plugin",
          developer_name: "synthetic-developer",
          summary: "Synthetic summary",
          category: "development",
          tags: ["synthetic"],
          latest_version: "1.0.0",
          risk_tier: "standard",
          review_policy_version: "synthetic-policy-v1",
          published_at: "2026-08-25T00:00:00Z",
          architectures: ["windows-x64"],
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
    };
    const revocations: DesktopPluginRevocationListResponse = {
      generated_at: "2026-08-25T00:00:00Z",
      policy_version: "desktop-plugin-control-plane-v1",
      items: [],
    };

    expect(DESKTOP_PLUGIN_ARCHITECTURES).toEqual([
      "windows-x64",
      "windows-arm64",
    ]);
    expect(DESKTOP_PLUGIN_VERSION_STATUSES).toContain("quarantined");
    expect(DESKTOP_PLUGIN_PATHS.catalog).toBe("/desktop/plugins/catalog");
    expect(DESKTOP_PLUGIN_PATHS.reviewReport).toBe(
      "/developer/plugin-versions/{version_id}/review-report",
    );
    expect(DESKTOP_PLUGIN_PATHS.buildProof).toBe(
      "/developer/plugin-versions/{version_id}/build-proof",
    );
    expect(DESKTOP_PLUGIN_PATHS.migrationRetries).toBe(
      "/desktop/plugins/migration-retries",
    );
    expect(DESKTOP_PLUGIN_PATHS.adminRunners).toBe("/admin/plugin-review-runners");
    expect(DESKTOP_PLUGIN_PATHS.brokerAuthorize).toContain("broker/authorize");
    expect(catalog.items[0]?.latest_version).toBe("1.0.0");
    expect(revocations.items).toEqual([]);
  });
});
