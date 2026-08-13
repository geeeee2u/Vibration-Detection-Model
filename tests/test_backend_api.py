import pandas as pd
from fastapi.testclient import TestClient

from backend.main import create_app


def write_results(tmp_path: object) -> object:
    path = tmp_path / "results.csv"
    pd.DataFrame(
        [
            {
                "Timestamps": "2026-01-01 00:00:00",
                "Vibration": 1.0,
                "short_mean": 1.0,
                "anomaly_score": 0.1,
                "threshold": 0.2,
                "raw_anomaly": False,
                "confirmed_anomaly": False,
                "is_anomaly": False,
                "anomaly_type": "normal",
            }
        ]
    ).to_csv(path, index=False)
    return path


def write_metrics(tmp_path: object) -> object:
    path = tmp_path / "metrics.csv"
    pd.DataFrame(
        [
            {
                "anomaly_type": "normal",
                "recall": 0.0,
                "false_positive_rate": 0.003,
                "rows": 100,
            },
            {
                "anomaly_type": "repeated_spike",
                "recall": 1.0,
                "false_positive_rate": 0.0,
                "rows": 30,
            },
        ]
    ).to_csv(path, index=False)
    return path


def test_performance_endpoint_returns_persisted_metrics(tmp_path):
    """The dashboard must expose the persisted synthetic-evaluation summary."""
    app = create_app(
        results_path=write_results(tmp_path),
        settings_path=tmp_path / "settings.json",
        metrics_path=write_metrics(tmp_path),
        input_path=tmp_path / "input.xlsx",
    )

    response = TestClient(app).get("/api/performance")

    assert response.status_code == 200
    assert response.json()["patterns"] == [
        {
            "anomaly_type": "repeated_spike",
            "rows": 30,
            "detected_rows": 30,
            "recall": 1.0,
        }
    ]


def test_reanalyze_returns_performance_from_the_configured_metrics_file(tmp_path, monkeypatch):
    """Reanalysis must use its configured metrics path before returning dashboard data."""
    results_path = write_results(tmp_path)
    metrics_path = tmp_path / "metrics.csv"
    app = create_app(
        results_path=results_path,
        settings_path=tmp_path / "settings.json",
        metrics_path=metrics_path,
        input_path=tmp_path / "input.xlsx",
    )
    result = pd.DataFrame({"is_anomaly": [False, True]})

    def fake_rerun(_settings, _input_path, _output_path, output_metrics_path):
        pd.DataFrame(
            [
                {
                    "anomaly_type": "normal",
                    "recall": 0.0,
                    "false_positive_rate": 0.02,
                    "rows": 10,
                },
                {
                    "anomaly_type": "std_increase",
                    "recall": 0.5,
                    "false_positive_rate": 0.0,
                    "rows": 20,
                },
            ]
        ).to_csv(output_metrics_path, index=False)
        return result

    monkeypatch.setattr("backend.main.rerun_analysis", fake_rerun)

    response = TestClient(app).post("/api/reanalyze", json={})

    assert response.status_code == 200
    assert response.json() == {
        "rows": 2,
        "confirmed_alarm_count": 1,
        "performance": {
            "normal_false_positive_rate": 0.02,
            "overall_recall": 0.5,
            "patterns": [
                {
                    "anomaly_type": "std_increase",
                    "rows": 20,
                    "detected_rows": 10,
                    "recall": 0.5,
                }
            ],
        },
    }
