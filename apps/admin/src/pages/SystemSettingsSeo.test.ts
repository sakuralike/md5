import { describe, expect, it, vi } from "vitest";
import type { SeoSettings } from "@password-detective/api-contract";
import { apiRequest } from "../services/api";
import { getSeoSettings, saveSeoSettings } from "../services/settings";
import {
  cloneSeoSettingsForm,
  createSeoSettingsForm,
  seoSettingsPayload,
} from "../lib/seoSettingsForm";

vi.mock("../services/api", () => ({
  apiRequest: vi.fn((path: string) => Promise.resolve({ path })),
}));

const mockedApiRequest = vi.mocked(apiRequest);
const settings: SeoSettings = {
  enabled: true,
  indexing_enabled: true,
  home_title: "密码侦探社首页",
  keywords: ["密码", "压缩包", "社区"],
  description: "合成测试描述",
  title_separator: "·",
  default_image_url: "https://synthetic.example.com/seo.png",
  open_graph_enabled: true,
  sitemap_enabled: true,
};

describe("Admin SEO settings", () => {
  it("normalizes keyword input without changing the persisted field contract", () => {
    const form = createSeoSettingsForm({ ...settings, keywords: ["密码", "压缩包"] });
    form.keywords_text = " 密码, 社区，压缩包, ,社区 ";

    expect(seoSettingsPayload(form)).toEqual({
      ...settings,
      keywords: ["密码", "社区", "压缩包"],
    });
  });

  it("clones the loaded baseline so reset data is isolated from edits", () => {
    const form = createSeoSettingsForm(settings);
    const baseline = cloneSeoSettingsForm(form);
    form.home_title = "临时编辑标题";
    form.keywords_text = "临时关键词";

    expect(baseline.home_title).toBe("密码侦探社首页");
    expect(baseline.keywords_text).toBe("密码, 压缩包, 社区");
  });

  it("reads SEO settings through the protected current-settings endpoint", async () => {
    await getSeoSettings("synthetic-admin-token");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/seo",
      {},
      "synthetic-admin-token",
    );
  });

  it("saves SEO settings with an idempotency key", async () => {
    await saveSeoSettings(settings, "synthetic-admin-token", "synthetic-seo-idempotency-1");
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/admin/settings/seo",
      {
        method: "PUT",
        headers: { "Idempotency-Key": "synthetic-seo-idempotency-1" },
        body: JSON.stringify(settings),
      },
      "synthetic-admin-token",
    );
  });
});