import type { CommunitySeoProjection, PublicSeoConfig } from "@password-detective/api-contract";

export type SeoRouteScope = "public" | "guest" | "private";
export type SeoContentKind = "post" | "group";

export interface CommunitySeoMetadataInput {
  kind: SeoContentKind;
  projection: CommunitySeoProjection;
}

export interface SeoMetadataInput {
  path: string;
  seo: PublicSeoConfig;
  siteName: string;
  origin: string;
  scope?: SeoRouteScope;
  title?: string;
  community?: CommunitySeoMetadataInput;
}

export interface SeoOpenGraphMetadata {
  type: "website" | "article";
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

function safeCommunityPathUrl(value: string | null, origin: string | null): string | null {
  if (!value || !origin || !value.startsWith("/") || value.startsWith("//")) return null;
  if (value.includes("?") || value.includes("#") || value.includes("\\")) return null;
  if ([...value].some((character) => character.codePointAt(0)! < 32)) return null;
  try {
    const url = new URL(value, `${origin}/`);
    return url.origin === origin ? url.toString() : null;
  } catch {
    return null;
  }
}

function safeCommunityImageUrl(value: string | null, origin: string | null): string | null {
  if (!value) return null;
  if (value.startsWith("/") && !value.startsWith("//")) {
    return safeCommunityPathUrl(value, origin);
  }
  return safeImageUrl(value);
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
  const origin = safeOrigin(input.origin);
  const community = input.community;
  const useCommunityMetadata = Boolean(input.seo.enabled && community?.projection.eligible);
  const communityTitle = useCommunityMetadata
    ? normalizedText(community?.projection.title ?? "")
    : "";
  const title = communityTitle
    ? `${communityTitle} ${input.seo.title_separator} ${siteName}`
    : resolvedTitle(input, siteName);
  const indexable = input.scope === "public"
    && input.seo.enabled
    && input.seo.indexing_enabled
    && (community?.projection.indexable ?? true);
  const communityUrl = useCommunityMetadata
    ? safeCommunityPathUrl(community?.projection.canonical_path ?? null, origin)
    : null;
  const canonical = useCommunityMetadata
    ? communityUrl
    : indexable && origin
      ? new URL(input.path, `${origin}/`).toString()
      : null;

  if (!indexable && !useCommunityMetadata) {
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

  const description = useCommunityMetadata
    ? normalizedText(community?.projection.description ?? "") || null
    : normalizedText(input.seo.description) || null;
  const keywords = (useCommunityMetadata ? community?.projection.keywords ?? [] : input.seo.keywords)
    .map((keyword) => normalizedText(keyword))
    .filter(Boolean)
    .join(", ") || null;
  const image = useCommunityMetadata
    ? safeCommunityImageUrl(community?.projection.og_image_url ?? null, origin)
      ?? safeImageUrl(input.seo.default_image_url)
    : safeImageUrl(input.seo.default_image_url);

  return {
    indexable,
    title,
    description,
    keywords,
    canonical,
    robots: indexable ? "index, follow" : "noindex, nofollow",
    openGraph:
      input.seo.open_graph_enabled && canonical && description
        ? {
            type: community?.kind === "post" ? "article" : "website",
            title,
            description,
            url: canonical,
            image,
          }
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
    appendMeta(documentRef, "property", "og:type", metadata.openGraph.type);
    appendMeta(documentRef, "property", "og:site_name", resolvedSiteName(siteName));
    appendMeta(documentRef, "property", "og:title", metadata.openGraph.title);
    appendMeta(documentRef, "property", "og:description", metadata.openGraph.description);
    appendMeta(documentRef, "property", "og:url", metadata.openGraph.url);
    if (metadata.openGraph.image) appendMeta(documentRef, "property", "og:image", metadata.openGraph.image);
  }
}
