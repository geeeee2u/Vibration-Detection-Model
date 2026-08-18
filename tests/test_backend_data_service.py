import pandas as pd
import pytest

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


def test_rerun_analysis_keeps_existing_files_when_synthetic_evaluation_fails(tmp_path, monkeypatch):
    """A failed synthetic evaluation must not publish only the new analysis result."""
    source = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-01 00:00:00"]),
            "Vibration": [1.0],
        }
    )
    result = source.assign(is_anomaly=True)
    output_path = tmp_path / "results.csv"
    metrics_path = tmp_path / "metrics.csv"
    output_path.write_text("previous-results\n", encoding="utf-8")
    metrics_path.write_text("previous-metrics\n", encoding="utf-8")

    monkeypatch.setattr("backend.analysis_service.load_case1", lambda _: source)
    monkeypatch.setattr("backend.analysis_service.detect_anomalies", lambda *_args, **_kwargs: result)

    def fail_evaluation(*_args, **_kwargs):
        raise RuntimeError("synthetic evaluation failed")

    monkeypatch.setattr("backend.analysis_service.evaluate_synthetic_test", fail_evaluation)

    with pytest.raises(RuntimeError, match="synthetic evaluation failed"):
        rerun_analysis(ModelSettings(), "input.xlsx", output_path, metrics_path)

    assert output_path.read_text(encoding="utf-8") == "previous-results\n"
    assert metrics_path.read_text(encoding="utf-8") == "previous-metrics\n"


def test_rerun_analysis_from_repository_uses_case_records_and_publishes_new_run(monkeypatch):
    """Repository reanalysis must analyze stored raw data and publish its result atomically."""
    # Removing repository loading or result publication would make this test fail.
    from backend.analysis_service import rerun_analysis_from_repository

    source = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-01 00:00:00"]),
            "Vibration": [1.0],
        }
    )
    result = source.assign(is_anomaly=False)
    metrics = pd.DataFrame(
        [{"anomaly_type": "normal", "recall": 0.0, "false_positive_rate": 0.003, "rows": 1}]
    )

    class Repository:
        def __init__(self):
            self.loaded_case = None
            self.published = None

        def load_raw_data(self, source_case):
            self.loaded_case = source_case
            return source

        def replace_active_run(self, published_result, published_metrics, settings):
            self.published = (published_result, published_metrics, settings)

    repository = Repository()
    monkeypatch.setattr("backend.analysis_service.detect_anomalies", lambda *_args, **_kwargs: result)
    monkeypatch.setattr("backend.analysis_service.evaluate_synthetic_test", lambda *_args, **_kwargs: (source, metrics))

    returned = rerun_analysis_from_repository(ModelSettings(), repository, source_case="Case1")

    assert repository.loaded_case == "Case1"
    assert returned.equals(result)
    assert repository.published[0].equals(result)
    assert repository.published[1].equals(metrics)
    assert repository.published[2] == ModelSettings()


def test_bootstrap_command_requires_database_url_before_loading_input(monkeypatch, capsys):
    """The CLI must stop clearly before loading Excel when DATABASE_URL is not configured."""
    # Moving environment validation after data loading would make this test fail.
    from scripts.bootstrap_postgres import main

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as error:
        main(["--input", "AI Model Raw Data.xlsx"])

    assert error.value.code == 2
    assert "DATABASE_URL environment variable is required" in capsys.readouterr().err
