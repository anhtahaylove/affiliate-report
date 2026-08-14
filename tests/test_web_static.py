import re
from pathlib import Path


def service_worker_source() -> str:
    return (Path(__file__).parents[1] / "web" / "public" / "sw.js").read_text(encoding="utf-8")


def global_css_source() -> str:
    return (Path(__file__).parents[1] / "web" / "src" / "app" / "globals.css").read_text(encoding="utf-8")


def test_production_ui_uses_affiliate_report_brand_only():
    web_root = Path(__file__).parents[1] / "web" / "src"
    shell = (web_root / "components" / "app-shell.tsx").read_text(encoding="utf-8")
    layout = (web_root / "app" / "layout.tsx").read_text(encoding="utf-8")
    manifest = (web_root / "app" / "manifest.ts").read_text(encoding="utf-8")

    assert "<strong>Affiliate Report</strong>" in shell
    assert "TikTok Affiliate" not in shell + layout + manifest


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def css_color(block: str, token: str) -> str:
    match = re.search(rf"--{re.escape(token)}:\s*(#[0-9a-fA-F]{{6}});", block)
    assert match, f"Missing solid color token --{token}"
    return match.group(1)


def test_service_worker_bypasses_private_routes_before_cache_handling():
    source = service_worker_source()

    assert 'const BYPASS_PREFIXES = ["/api/", "/auth/", "/health"]' in source
    assert source.index("shouldBypass(event.request)") < source.index("event.respondWith(")
    assert "if (response.ok)" in source


def test_service_worker_cache_is_versioned_and_covers_every_public_route():
    source = service_worker_source()

    assert 'const CACHE_PREFIX = "tiktok-affiliate-report-shell-"' in source
    assert "__APP_VERSION__" in source
    for route in (
        '"/"',
        '"/analytics/"',
        '"/orders/"',
        '"/imports/"',
        '"/targets/"',
        '"/accounts/"',
        '"/settings/preferences/"',
        '"/settings/data/"',
        '"/settings/update/"',
        '"/settings/users/"',
        '"/offline.html"',
    ):
        assert route in source
    assert "key.startsWith(CACHE_PREFIX)" in source


def test_service_worker_navigation_failure_uses_offline_page_not_dashboard():
    source = service_worker_source()

    assert 'caches.match("/offline.html")' in source
    assert 'caches.match("/")' not in source


def test_focus_and_muted_text_tokens_meet_wcag_contrast_thresholds():
    source = global_css_source()
    light = source.split("@media (prefers-color-scheme: dark)", 1)[0]
    dark = source.split(':root[data-theme="dark"] {', 1)[1].split("}", 1)[0]

    for theme in (light, dark):
        background = css_color(theme, "bg")
        surface = css_color(theme, "surface")
        muted = css_color(theme, "text-muted")
        focus = css_color(theme, "focus-ring")
        assert contrast_ratio(muted, background) >= 4.5
        assert contrast_ratio(muted, surface) >= 4.5
        assert contrast_ratio(focus, background) >= 3
        assert contrast_ratio(focus, surface) >= 3
