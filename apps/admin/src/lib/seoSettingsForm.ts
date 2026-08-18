import type { SeoSettings, SeoTitleSeparator } from "@password-detective/api-contract";

export interface SeoSettingsForm {
  enabled: boolean;
  indexing_enabled: boolean;
  home_title: string;
  keywords_text: string;
  description: string;
  title_separator: SeoTitleSeparator;
  default_image_url: string;
  open_graph_enabled: boolean;
  sitemap_enabled: boolean;
}

export function createSeoSettingsForm(settings: SeoSettings): SeoSettingsForm {
  return {
    enabled: settings.enabled,
    indexing_enabled: settings.indexing_enabled,
    home_title: settings.home_title,
    keywords_text: settings.keywords.join(", "),
    description: settings.description,
    title_separator: settings.title_separator,
    default_image_url: settings.default_image_url,
    open_graph_enabled: settings.open_graph_enabled,
    sitemap_enabled: settings.sitemap_enabled,
  };
}

export function cloneSeoSettingsForm(form: SeoSettingsForm): SeoSettingsForm {
  return { ...form };
}

function normalizeKeywords(value: string): string[] {
  return [...new Set(value.split(/[,，]/u).map((keyword) => keyword.trim()).filter(Boolean))];
}

export function seoSettingsPayload(form: SeoSettingsForm): SeoSettings {
  return {
    enabled: form.enabled,
    indexing_enabled: form.indexing_enabled,
    home_title: form.home_title.trim(),
    keywords: normalizeKeywords(form.keywords_text),
    description: form.description.trim(),
    title_separator: form.title_separator,
    default_image_url: form.default_image_url.trim(),
    open_graph_enabled: form.open_graph_enabled,
    sitemap_enabled: form.sitemap_enabled,
  };
}