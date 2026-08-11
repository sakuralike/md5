from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_web_ui_does_not_override_tailwind_grid_utility() -> None:
    shared_styles = (ROOT / "packages/web-ui/src/styles.css").read_text(encoding="utf-8")
    web_styles = (ROOT / "apps/web/src/index.css").read_text(encoding="utf-8")

    assert re.search(r"(?m)^\s*\.grid\s*\{", shared_styles) is None
    assert ".hero, .grid" not in shared_styles
    assert re.search(r"(?m)^\s*\.grid\s*\{", web_styles) is None
    assert "  .grid >" not in web_styles


def test_admin_does_not_load_legacy_web_ui_styles() -> None:
    admin_entry = (ROOT / "apps/admin/src/main.ts").read_text(encoding="utf-8")

    assert '@password-detective/web-ui/styles.css' not in admin_entry
