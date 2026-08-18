import type { PublicSeoConfig } from "@password-detective/api-contract";
import { describe, expect, it } from "vitest";
import { buildSeoMetadata } from "./seo";

const seo: PublicSeoConfig = {
  enabled: true,
  indexing_enabled: true,
  home_title: "密码侦探社",
  keywords: ["压缩包", "密码", "社区"],
  description: "使用本地文件指纹查询压缩包密码证据。",
  title_separator: "|",
  default_image_url: "https://assets.synthetic.example/seo.png",
  open_graph_enabled: true,
};

describe("buildSeoMetadata", () => {
  it("generates canonical public home metadata without query or hash", () => {
    const metadata = buildSeoMetadata({
      path: "/",
      seo,
      siteName: "密码侦探社",
      origin: "https://example.synthetic/?session=secret#private",
      scope: "public",
    });

    expect(metadata.indexable).toBe(true);
    expect(metadata.title).toBe("密码侦探社");
    expect(metadata.canonical).toBe("https://example.synthetic/");
    expect(metadata.robots).toBe("index, follow");
    expect(metadata.description).toBe(seo.description);
    expect(metadata.keywords).toBe("压缩包, 密码, 社区");
    expect(metadata.openGraph).toEqual({
      title: "密码侦探社",
      description: seo.description,
      url: "https://example.synthetic/",
      image: "https://assets.synthetic.example/seo.png",
    });
  });

  it("uses the configured separator for whitelisted public routes", () => {
    const metadata = buildSeoMetadata({
      path: "/community",
      seo,
      siteName: "密码侦探社",
      origin: "https://example.synthetic",
      scope: "public",
      title: "社区",
    });

    expect(metadata.title).toBe("社区 | 密码侦探社");
    expect(metadata.canonical).toBe("https://example.synthetic/community");
  });

  it("keeps guest, private, and unlisted routes noindex without canonical or Open Graph", () => {
    for (const scope of ["guest", "private", undefined] as const) {
      const metadata = buildSeoMetadata({
        path: "/account/authorized-applications",
        seo,
        siteName: "密码侦探社",
        origin: "https://example.synthetic",
        scope,
      });

      expect(metadata.indexable).toBe(false);
      expect(metadata.robots).toBe("noindex, nofollow");
      expect(metadata.canonical).toBeNull();
      expect(metadata.openGraph).toBeNull();
    }
  });

  it("keeps API failures and disabled indexing on the safe noindex fallback", () => {
    const metadata = buildSeoMetadata({
      path: "/community",
      seo: { ...seo, enabled: false, indexing_enabled: false },
      siteName: "密码侦探社",
      origin: "not-a-valid-origin",
      scope: "public",
      title: "社区",
    });

    expect(metadata.indexable).toBe(false);
    expect(metadata.title).toBe("社区 | 密码侦探社");
    expect(metadata.robots).toBe("noindex, nofollow");
    expect(metadata.canonical).toBeNull();
    expect(metadata.description).toBeNull();
    expect(metadata.keywords).toBeNull();
    expect(metadata.openGraph).toBeNull();
  });
});
