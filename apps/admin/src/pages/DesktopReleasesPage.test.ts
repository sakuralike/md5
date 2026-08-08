import { renderToString } from "@vue/server-renderer";
import { createSSRApp } from "vue";
import { describe, expect, it, vi } from "vitest";
import DesktopReleasesPage from "./DesktopReleasesPage.vue";

vi.mock("../stores/auth", () => ({
  useAdminAuthStore: () => ({
    accessToken: "synthetic-admin-token",
  }),
}));

describe("DesktopReleasesPage", () => {
  it("renders the controlled desktop release workbench", async () => {
    const html = await renderToString(createSSRApp(DesktopReleasesPage));

    expect(html).toContain("桌面版本发布");
    expect(html).toContain("受控发布");
    expect(html).toContain("安全边界");
    expect(html).toContain("创建草稿并上传制品");
    expect(html).toContain("还没有桌面发布记录");
    expect(html).not.toContain("synthetic-admin-token");
  });
});
