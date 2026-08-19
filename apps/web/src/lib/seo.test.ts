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
      type: "website",
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

  it("uses eligible post metadata without opening dynamic content indexing", () => {
    const metadata = buildSeoMetadata({
      path: "/community/posts/synthetic-post-id",
      seo,
      siteName: "密码侦探社",
      origin: "https://example.synthetic",
      scope: "private",
      community: {
        kind: "post",
        projection: {
          eligible: true,
          indexable: false,
          title: "  合成公开主题  ",
          description: "  公开主题的 合成摘要。 ",
          keywords: ["社区", " 合成数据 "],
          canonical_path: "/community/posts/synthetic-post-id",
          og_image_url: "/media/synthetic-post.png",
        },
      },
    });

    expect(metadata).toEqual({
      indexable: false,
      title: "合成公开主题 | 密码侦探社",
      description: "公开主题的 合成摘要。",
      keywords: "社区, 合成数据",
      canonical: "https://example.synthetic/community/posts/synthetic-post-id",
      robots: "noindex, nofollow",
      openGraph: {
        type: "article",
        title: "合成公开主题 | 密码侦探社",
        description: "公开主题的 合成摘要。",
        url: "https://example.synthetic/community/posts/synthetic-post-id",
        image: "https://example.synthetic/media/synthetic-post.png",
      },
    });
  });

  it("uses the default share image for eligible public groups while retaining noindex", () => {
    const metadata = buildSeoMetadata({
      path: "/community/groups/synthetic-lab",
      seo,
      siteName: "密码侦探社",
      origin: "https://example.synthetic",
      scope: "private",
      community: {
        kind: "group",
        projection: {
          eligible: true,
          indexable: false,
          title: "合成研究组",
          description: "仅讨论合法授权场景。",
          keywords: [],
          canonical_path: "/community/groups/synthetic-lab",
          og_image_url: null,
        },
      },
    });

    expect(metadata.indexable).toBe(false);
    expect(metadata.robots).toBe("noindex, nofollow");
    expect(metadata.canonical).toBe("https://example.synthetic/community/groups/synthetic-lab");
    expect(metadata.openGraph).toEqual({
      type: "website",
      title: "合成研究组 | 密码侦探社",
      description: "仅讨论合法授权场景。",
      url: "https://example.synthetic/community/groups/synthetic-lab",
      image: seo.default_image_url,
    });
  });

  it("ignores ineligible and malformed community projections", () => {
    const ineligible = buildSeoMetadata({
      path: "/community/groups/private-lab",
      seo,
      siteName: "密码侦探社",
      origin: "https://example.synthetic",
      scope: "private",
      community: {
        kind: "group",
        projection: {
          eligible: false,
          indexable: false,
          title: "不得公开的群组",
          description: "不得公开的摘要",
          keywords: ["私密"],
          canonical_path: "/community/groups/private-lab",
          og_image_url: null,
        },
      },
    });
    const malformed = buildSeoMetadata({
      path: "/community/posts/synthetic-post-id",
      seo,
      siteName: "密码侦探社",
      origin: "https://example.synthetic",
      scope: "private",
      community: {
        kind: "post",
        projection: {
          eligible: true,
          indexable: false,
          title: "合成主题",
          description: "合成摘要",
          keywords: [],
          canonical_path: "https://external.synthetic/unsafe",
          og_image_url: "javascript:alert(1)",
        },
      },
    });

    expect(ineligible.description).toBeNull();
    expect(ineligible.keywords).toBeNull();
    expect(ineligible.canonical).toBeNull();
    expect(ineligible.openGraph).toBeNull();
    expect(malformed.canonical).toBeNull();
    expect(malformed.openGraph).toBeNull();
    expect(malformed.robots).toBe("noindex, nofollow");
  });
});
