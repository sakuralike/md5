import type { DesktopAnnouncement } from "@password-detective/api-contract";
import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it } from "vitest";
import { plainAnnouncementContent } from "@/lib/announcementContent";
import AnnouncementPopup from "./AnnouncementPopup.vue";

const announcement: DesktopAnnouncement = {
  id: "synthetic-announcement",
  title: "维护窗口提醒",
  content: "<p>服务将在 <strong>02:00</strong> 维护。</p>",
  content_type: "html",
  image_urls: ["/api/v1/desktop/announcements/assets/synthetic.webp"],
  action_label: "查看说明",
  action_url: "https://synthetic.example.com/notice",
  sort_order: 10,
  starts_at: null,
  ends_at: null,
  status: "published",
  revision: 2,
  created_at: "2026-08-14T00:00:00Z",
  updated_at: "2026-08-14T00:00:00Z",
  published_at: "2026-08-14T00:00:00Z",
  archived_at: null,
};

describe("AnnouncementPopup", () => {
  it("renders a bottom-right announcement without injecting HTML", async () => {
    const html = await renderToString(
      createSSRApp(AnnouncementPopup, { initialAnnouncements: [announcement], autoload: false }),
    );

    expect(html).toContain("网站公告");
    expect(html).toContain("维护窗口提醒");
    expect(html).toContain("服务将在 02:00 维护。");
    expect(html).not.toContain("<strong>02:00</strong>");
    expect(html).toContain("fixed bottom-4 right-4");
    expect(html).toContain("noopener noreferrer");
  });

  it("converts configured HTML content to plain text", () => {
    expect(plainAnnouncementContent("<p>合成 <em>公告</em></p>")).toBe("合成 公告");
  });
});
