from __future__ import annotations

import xml.etree.ElementTree as ET

from password_detective.db.models.system_setting import SystemSetting


def _set_seo(client, **overrides: object) -> None:
    defaults = {
        "enabled": True,
        "indexing_enabled": True,
        "home_title": "Synthetic Password Detective",
        "keywords": ["synthetic", "hash"],
        "description": "Synthetic public discovery site.",
        "title_separator": "|",
        "default_image_url": "/assets/seo.webp",
        "open_graph_enabled": True,
        "sitemap_enabled": True,
    }
    defaults.update(overrides)
    with client.app.state.database.session_factory() as db:
        db.merge(SystemSetting(key="seo_settings", value_json={"value": defaults}))
        db.commit()


def test_robots_txt_is_closed_by_safe_default(client):
    response = client.get("/api/v1/site/robots.txt", headers={"Host": "attacker.example"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "User-agent: *\nDisallow: /\n"


def test_robots_txt_allows_public_indexing_and_advertises_configured_sitemap(client):
    _set_seo(client)

    response = client.get("/api/v1/site/robots.txt", headers={"Host": "attacker.example"})

    assert response.status_code == 200
    assert response.text == (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Disallow: /account\n"
        "Disallow: /community/messages\n"
        "Disallow: /community/settings\n"
        "Disallow: /community/search\n"
        "Disallow: /oauth\n"
        "Disallow: /admin\n"
        "Sitemap: http://localhost:5173/sitemap.xml\n"
    )


def test_sitemap_xml_contains_only_registered_public_routes(client):
    _set_seo(client)

    response = client.get("/api/v1/site/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.content)
    locations = [element.text for element in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert locations == ["http://localhost:5173/", "http://localhost:5173/community"]
    assert all("?" not in location and "#" not in location for location in locations)
    assert all("/login" not in location and "/admin" not in location for location in locations)


def test_sitemap_xml_is_empty_when_indexing_or_sitemap_is_disabled(client):
    _set_seo(client, indexing_enabled=False)
    assert "<url>" not in client.get("/api/v1/site/sitemap.xml").text

    _set_seo(client, indexing_enabled=True, sitemap_enabled=False)
    assert "<url>" not in client.get("/api/v1/site/sitemap.xml").text
