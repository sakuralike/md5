import type { PublicSeoConfig } from "@password-detective/api-contract";

export type SeoRouteScope = "public" | "guest" | "private";

export interface SeoMetadataInput {
  path: string;
  seo: PublicSeoConfig;
  siteName: string;
  origin: string;
  scope?: SeoRouteScope;
  title?: string;
}

export interface SeoOpenGraphMetadata {
  title: string;
  description: string;
  url: string;
  image: string | null;
}

export interface SeoMetadata {
  indexable: boolean;
  title: string;
  description: string | null;
  keywords: string | null;
  canonical: string | null;
  robots: "index, follow" | "noindex, nofollow";
  openGraph: SeoOpenGraphMetadata | null;
}

function normalizedText(value: string): string {
  return value.trim().replace(/\s+/gu, " ");
}

function safeOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.origin : null;
  } catch {
    return null;
  }
}

function safeImageUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function resolvedSiteName(value: string): string {
  return normalizedText(value) || "密码侦探社";
}

function resolvedTitle(input: SeoMetadataInput, siteName: string): string {
  const routeTitle = normalizedText(input.title ?? "");
  if (routeTitle) return `${routeTitle} ${input.seo.title_separator} ${siteName}`;
  return normalizedText(input.seo.home_title) || siteName;
}

export function buildSeoMetadata(input: SeoMetadataInput): SeoMetadata {
  const siteName = resolvedSiteName(input.siteName);
  const title = resolvedTitle(input, siteName);
  const indexable = input.scope === "public" && input.seo.enabled && input.seo.indexing_enabled;
  const origin = safeOrigin(input.origin);
  const canonical = indexable && origin ? new URL(input.path, `${origin}/`).toString() : null;

  if (!indexable) {
    return {
      indexable: false,
      title,
      description: null,
      keywords: null,
      canonical: null,
      robots: "noindex, nofollow",
      openGraph: null,
    };
  }

  const description = normalizedText(input.seo.description) || null;
  const keywords = input.seo.keywords
    .map((keyword) => normalizedText(keyword))
    .filter(Boolean)
    .join(", ") || null;
  const image = safeImageUrl(input.seo.default_image_url);

  return {
    indexable: true,
    title,
    description,
    keywords,
    canonical,
    robots: "index, follow",
    openGraph:
      input.seo.open_graph_enabled && canonical && description
        ? { title, description, url: canonical, image }
        : null,
  };
}

function appendMeta(documentRef: Document, attribute: "name" | "property", key: string, content: string): void {
  const element = documentRef.createElement("meta");
  element.setAttribute(attribute, key);
  element.setAttribute("content", content);
  element.dataset.passwordDetectiveSeo = "true";
  documentRef.head.append(element);
}

export function applySeoMetadata(documentRef: Document, metadata: SeoMetadata, siteName: string): void {
  documentRef.title = metadata.title;
  documentRef.head
    .querySelectorAll(
      '[data-password-detective-seo="true"], meta[name="description"], meta[name="keywords"], meta[name="robots"], link[rel="canonical"], meta[property^="og:"]',
    )
    .forEach((element) => element.remove());

  appendMeta(documentRef, "name", "robots", metadata.robots);
  if (metadata.description) appendMeta(documentRef, "name", "description", metadata.description);
  if (metadata.keywords) appendMeta(documentRef, "name", "keywords", metadata.keywords);
  if (metadata.canonical) {
    const link = documentRef.createElement("link");
    link.setAttribute("rel", "canonical");
    link.setAttribute("href", metadata.canonical);
    link.dataset.passwordDetectiveSeo = "true";
    documentRef.head.append(link);
  }
  if (metadata.openGraph) {
    appendMeta(documentRef, "property", "og:type", "website");
    appendMeta(documentRef, "property", "og:site_name", resolvedSiteName(siteName));
    appendMeta(documentRef, "property", "og:title", metadata.openGraph.title);
    appendMeta(documentRef, "property", "og:description", metadata.openGraph.description);
    appendMeta(documentRef, "property", "og:url", metadata.openGraph.url);
    if (metadata.openGraph.image) appendMeta(documentRef, "property", "og:image", metadata.openGraph.image);
  }
}
