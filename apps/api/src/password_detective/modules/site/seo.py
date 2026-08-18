from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

from sqlalchemy.orm import Session

from password_detective.modules.admin.seo_settings import default_seo_settings
from password_detective.modules.admin.setting_schemas import SeoSettings
from password_detective.modules.site.service import _setting_value

SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


@dataclass(frozen=True)
class PublicSitemapRoute:
    path: str
    seo_indexable: bool


PUBLIC_ROUTE_REGISTRY = (
    PublicSitemapRoute(path="/", seo_indexable=True),
    PublicSitemapRoute(path="/community", seo_indexable=True),
)
ROBOTS_DISALLOW_PATHS = (
    "/login",
    "/register",
    "/account",
    "/community/messages",
    "/community/settings",
    "/community/search",
    "/oauth",
    "/admin",
)


def seo_settings_for_files(db: Session) -> SeoSettings:
    defaults = default_seo_settings()
    raw_settings = _setting_value(db, "seo_settings", defaults.model_dump(mode="json"))
    try:
        return SeoSettings.model_validate(raw_settings)
    except (TypeError, ValueError):
        return defaults


def build_robots_txt(settings: SeoSettings, *, public_origin: str) -> str:
    if not settings.enabled or not settings.indexing_enabled:
        return "User-agent: *\nDisallow: /\n"

    lines = ["User-agent: *", "Allow: /"]
    lines.extend(f"Disallow: {path}" for path in ROBOTS_DISALLOW_PATHS)
    if settings.sitemap_enabled:
        lines.append(f"Sitemap: {public_origin}/sitemap.xml")
    return "\n".join(lines) + "\n"


def build_sitemap_xml(settings: SeoSettings, *, public_origin: str) -> bytes:
    root = ElementTree.Element("urlset", {"xmlns": SITEMAP_NAMESPACE})
    if settings.enabled and settings.indexing_enabled and settings.sitemap_enabled:
        for route in PUBLIC_ROUTE_REGISTRY:
            if not route.seo_indexable:
                continue
            url = ElementTree.SubElement(root, "url")
            ElementTree.SubElement(url, "loc").text = f"{public_origin}{route.path}"
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
