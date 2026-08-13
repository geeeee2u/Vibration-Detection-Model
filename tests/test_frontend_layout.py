from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_frontend_pages_keep_live_data_targets():
    required = {
        "overview.html": ["data-page=\"overview\"", "overview-current-vibration", "overview-trend-chart"],
        "analysis.html": ["data-page=\"analysis\"", "analysis-trend-chart", "analysis-rows"],
        "alarms.html": ["data-page=\"alarms\"", "alarm-rows", "alarm-detail"],
        "performance.html": ["data-page=\"performance\"", "performance-fpr", "performance-pattern-rows"],
        "settings.html": ["data-page=\"settings\"", "settings-form", "현재 모델에서 지원하지 않음"],
    }
    for filename, targets in required.items():
        html = (ROOT / "frontend" / filename).read_text(encoding="utf-8")
        for target in targets:
            assert target in html
