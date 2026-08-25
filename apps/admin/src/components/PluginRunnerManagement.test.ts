import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import PluginRunnerManagement from "./PluginRunnerManagement.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-runner-admin-token" }),
}));
vi.mock("../services/pluginReviews", () => ({
  listPluginRunners: vi.fn().mockResolvedValue({ items: [] }),
  getPluginReviewPolicy: vi.fn().mockResolvedValue({
    version: 0,
    policy_version: "desktop-plugin-review-policy-v1",
    static_engine_version: "desktop-plugin-static-review-v1",
    dynamic_engine_version: "desktop-plugin-dynamic-review-v1",
    static_lease_seconds: 300,
    dynamic_lease_seconds: 300,
    task_token_seconds: 900,
    maximum_static_attempts: 3,
    maximum_dynamic_attempts: 3,
    runner_offline_seconds: 90,
    revocation_refresh_hours: 6,
    revocation_max_stale_hours: 168,
    updated_at: null,
    updated_by: null,
  }),
  savePluginReviewPolicy: vi.fn(),
  createPluginRunner: vi.fn(),
  revokePluginRunner: vi.fn(),
}));

describe("PluginRunnerManagement", () => {
  it("renders runner identity, health and one-time registration controls", async () => {
    const html = await renderToString(createSSRApp(PluginRunnerManagement));
    expect(html).toContain("Windows 动态审核执行器");
    expect(html).toContain("客户端证书 SHA-256");
    expect(html).toContain("登记 Runner");
    expect(html).not.toContain("synthetic-runner-admin-token");
  });
});
