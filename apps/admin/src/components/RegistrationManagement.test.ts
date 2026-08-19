import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import RegistrationManagement from "./RegistrationManagement.vue";

vi.mock("../stores/auth", () => ({ useAdminAuthStore: () => ({ accessToken: "synthetic" }) }));
vi.mock("../services/registration", () => ({
  getRegistrationPolicy: vi.fn(),
  saveRegistrationPolicy: vi.fn(),
  listRegistrationInvites: vi.fn(),
  createRegistrationInvite: vi.fn(),
  revokeRegistrationInvite: vi.fn(),
}));

describe("RegistrationManagement", () => {
  it("renders registration policy and one-time invite controls", async () => {
    const html = await renderToString(createSSRApp(RegistrationManagement));

    expect(html).toContain("注册策略与邀请码");
    expect(html).toContain("保存注册策略");
    expect(html).toContain("生成邀请码");
    expect(html).toContain("明文仅在创建成功后显示一次");
  });
});
