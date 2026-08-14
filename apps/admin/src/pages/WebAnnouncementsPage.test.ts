import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import WebAnnouncementsPage from "./WebAnnouncementsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/webAnnouncements", () => ({
  listDesktopAnnouncements: vi.fn().mockResolvedValue({ items: [] }),
  buildDesktopAnnouncementPayload: vi.fn(),
  createDesktopAnnouncement: vi.fn(),
  updateDesktopAnnouncement: vi.fn(),
  publishDesktopAnnouncement: vi.fn(),
  archiveDesktopAnnouncement: vi.fn(),
}));

describe("WebAnnouncementsPage", () => {
  it("renders the desktop announcement management workbench", async () => {
    const html = await renderToString(createSSRApp(WebAnnouncementsPage));
    expect(html).toContain("Web 端公告管理");
    expect(html).toContain("新建公告草稿");
    expect(html).toContain("正在加载公告");
    expect(html).toContain("图片点击链接（可选）");
    expect(html).toContain("点击公告图片时打开");
    expect(html).toContain("自动关闭秒数");
    expect(html).toContain("设置为 0 时不自动关闭");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
