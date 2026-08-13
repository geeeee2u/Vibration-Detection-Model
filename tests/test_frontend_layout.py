from pathlib import Path
import re


ROOT = Path(__file__).parents[1]


def test_frontend_pages_keep_live_data_targets():
    pages = {
        "overview.html": "overview",
        "analysis.html": "analysis",
        "alarms.html": "alarms",
        "performance.html": "performance",
        "settings.html": "settings",
    }
    for filename, page in pages.items():
        html = (ROOT / "frontend" / filename).read_text(encoding="utf-8")
        assert f'data-page="{page}"' in html

    script = (ROOT / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")
    for target in ("overview-current-vibration", "overview-trend-chart", "analysis-trend-chart", "analysis-rows", "alarm-rows", "alarm-detail", "performance-fpr", "performance-pattern-rows", "settings-form"):
        assert target in script


def test_navigation_supports_all_stitch_alarm_menu_labels():
    script = (ROOT / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")
    for label in ("알람 내역", "알람 이력", "경보 이력"):
        assert f'"{label}": "/alarms"' in script


def test_each_page_has_static_dashboard_navigation_routes():
    expected_routes = ['href="/"', 'href="/analysis"', 'href="/alarms"', 'href="/performance"', 'href="/settings"']
    for filename in ("overview.html", "analysis.html", "alarms.html", "performance.html", "settings.html"):
        html = (ROOT / "frontend" / filename).read_text(encoding="utf-8")
        navigation = re.search(r"<nav\b.*?</nav>", html, flags=re.DOTALL)
        assert navigation, f"{filename} has no navigation"
        for route in expected_routes:
            assert route in navigation.group(0), f"{filename} is missing {route}"


def test_frontend_includes_account_switching_and_technician_settings_denial():
    script = (ROOT / "frontend" / "assets" / "app.js").read_text(encoding="utf-8")

    assert "data-account-control" in script
    assert "/api/auth/login" in script
    assert "/api/auth/logout" in script
    assert "해당 계정으로는 접근할 수 없습니다." in script


def test_analysis_page_loads_chartjs_before_the_dashboard_script():
    html = (ROOT / "frontend" / "analysis.html").read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/npm/chart.js" in html


def test_performance_page_has_an_explicit_dark_background():
    html = (ROOT / "frontend" / "performance.html").read_text(encoding="utf-8")

    assert '<body data-page="performance" class="bg-background' in html
