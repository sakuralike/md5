import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import DesktopAnnouncementsPage from "./DesktopAnnouncementsPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({ accessToken: "synthetic-admin-token" }),
}));

vi.mock("../services/desktopAnnouncements", () => ({
  listDesktopAnnouncements: vi.fn().mockResolvedValue({ items: [] }),
  buildDesktopAnnouncementPayload: vi.fn(),
  createDesktopAnnouncement: vi.fn(),
  updateDesktopAnnouncement: vi.fn(),
  publishDesktopAnnouncement: vi.fn(),
  archiveDesktopAnnouncement: vi.fn(),
}));

describe("DesktopAnnouncementsPage", () => {
  it("renders the desktop announcement management workbench", async () => {
    const html = await renderToString(createSSRApp(DesktopAnnouncementsPage));
    expect(html).toContain("桌面端公告管理");
    expect(html).toContain("新建公告草稿");
    expect(html).toContain("正在加载公告");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
