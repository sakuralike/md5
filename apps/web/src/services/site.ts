import type { HomeDiscoveryResponse, PublicSiteConfig } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function createDefaultPublicSiteConfig(): PublicSiteConfig {
  return {
    site_name: "密码侦探社",
    site_logo_url: "",
    navigation: [
      { label: "首页", path: "/", enabled: true, requires_auth: false },
      { label: "社区", path: "/community", enabled: true, requires_auth: false },
    ],
    seo: {
      enabled: false,
      indexing_enabled: false,
      home_title: "密码侦探社",
      keywords: [],
      description: "",
      title_separator: "-",
      default_image_url: "",
      open_graph_enabled: false,
    },
  };
}

export function getPublicSiteConfig(): Promise<PublicSiteConfig> {
  return apiRequest<PublicSiteConfig>("/site/config");
}

export function getHomeDiscovery(): Promise<HomeDiscoveryResponse> {
  return apiRequest<HomeDiscoveryResponse>("/site/home-discovery");
}
