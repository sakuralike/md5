import type { HomeDiscoveryResponse, PublicSiteConfig } from "@password-detective/api-contract";
import { apiRequest } from "./api";

export function getPublicSiteConfig(): Promise<PublicSiteConfig> {
  return apiRequest<PublicSiteConfig>("/site/config");
}

export function getHomeDiscovery(): Promise<HomeDiscoveryResponse> {
  return apiRequest<HomeDiscoveryResponse>("/site/home-discovery");
}
