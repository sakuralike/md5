import { describe, expect, it } from "vitest";
import { buildDesktopAnnouncementPayload } from "./desktopAnnouncements";

describe("buildDesktopAnnouncementPayload", () => {
  it("allows an image click link without requiring visible button text", () => {
    const payload = buildDesktopAnnouncementPayload({
      title: "合成桌面公告",
      content: "仅用于自动化测试。",
      contentType: "text",
      imageUrlsText: "/api/v1/desktop/announcements/assets/synthetic.png",
      actionLabel: "",
      actionUrl: "https://synthetic.example/notice",
      sortOrder: 0,
      startsAt: "",
      endsAt: "",
    });

    expect(payload.action_label).toBeNull();
    expect(payload.action_url).toBe("https://synthetic.example/notice");
  });
});
