import pandas as pd

from backend.analysis_service import rerun_analysis
from backend.config import ModelSettings
from backend.data_service import performance_payload


def test_performance_payload_calculates_overall_recall(tmp_path):
    """Synthetic pattern detections must be summarized independently of normal rows."""
    metrics = pd.DataFrame(
        [
            {"anomaly_type": "normal", "recall": 0.0, "false_positive_rate": 0.003, "rows": 100},
            {"anomaly_type": "repeated_spike", "recall": 1.0, "false_positive_rate": 0.0, "rows": 30},
            {"anomaly_type": "std_increase", "recall": 0.5, "false_positive_rate": 0.0, "rows": 30},
        ]
    )
    path = tmp_path / "metrics.csv"
    metrics.to_csv(path, index=False)

    payload = performance_payload(path)

    assert payload["normal_false_positive_rate"] == 0.003
    assert payload["overall_recall"] == 0.75
    assert payload["patterns"][0]["detected_rows"] == 30


def test_rerun_analysis_persists_synthetic_metrics_after_evaluation(tmp_path, monkeypatch):
    """A successful reanalysis must make both dashboard result files available."""
    source = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-01 00:00:00"]),
            "Vibration": [1.0],
        }
    )
    result = source.assign(is_anomaly=False)
    metrics = pd.DataFrame(
        [
            {
                "anomaly_type": "normal",
                "recall": 0.0,
                "false_positive_rate": 0.003,
                "rows": 1,
            }
        ]
    )
    monkeypatch.setattr("backend.analysis_service.load_case1", lambda _: source)
    monkeypatch.setattr("backend.analysis_service.detect_anomalies", lambda *_args, **_kwargs: result)
    monkeypatch.setattr("backend.analysis_service.evaluate_synthetic_test", lambda *_args, **_kwargs: (source, metrics))

    output_path = tmp_path / "results.csv"
    metrics_path = tmp_path / "metrics.csv"
    rerun_analysis(ModelSettings(), "input.xlsx", output_path, metrics_path)

    assert output_path.exists()
    assert metrics_path.exists()
