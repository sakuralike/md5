import { describe, expect, it } from "vitest";
import { buildWebAnnouncementPayload } from "./webAnnouncements";

describe("buildWebAnnouncementPayload", () => {
  it("allows an image click link without requiring visible button text", () => {
    const payload = buildWebAnnouncementPayload({
      title: "合成 Web 公告",
      content: "仅用于自动化测试。",
      contentType: "text",
      imageUrlsText: "/api/v1/web/announcements/assets/synthetic.png",
      actionLabel: "",
      actionUrl: "https://synthetic.example/notice",
      sortOrder: 0,
      autoCloseSeconds: 15,
      startsAt: "",
      endsAt: "",
    });

    expect(payload.action_label).toBeNull();
    expect(payload.action_url).toBe("https://synthetic.example/notice");
    expect(payload.auto_close_seconds).toBe(15);
  });

  it("maps zero seconds to disabled automatic close", () => {
    const payload = buildWebAnnouncementPayload({
      title: "不自动关闭公告",
      content: "合成测试内容。",
      contentType: "text",
      imageUrlsText: "",
      actionLabel: "",
      actionUrl: "",
      sortOrder: 0,
      autoCloseSeconds: 0,
      startsAt: "",
      endsAt: "",
    });
    expect(payload.auto_close_seconds).toBeNull();
  });
});
