import numpy as np
import pandas as pd

from synthetic_anomaly_evaluation import generate_synthetic_test, evaluate_synthetic_test


def _normal_frame(size=600):
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "Timestamps": pd.date_range("2026-01-01", periods=size, freq="s"),
            "Vibration": 3.3 + rng.normal(0, 0.02, size),
        }
    )


def test_synthetic_test_contains_all_requested_anomaly_types():
    result = generate_synthetic_test(_normal_frame(), anomaly_length=30, seed=42)
    expected = {"normal", "gradual_increase", "increase_1_to_5pct", "std_increase", "repeated_spike", "independent_random"}
    assert set(result["injected_type"].unique()) == expected
    assert int(result["injected_anomaly"].sum()) > 0


def test_evaluation_returns_recall_and_false_positive_metrics():
    results, metrics = evaluate_synthetic_test(_normal_frame(1200), anomaly_length=30, seed=42, n_estimators=50)
    assert {"injected_type", "raw_anomaly", "confirmed_anomaly"}.issubset(results.columns)
    assert {"anomaly_type", "recall", "false_positive_rate"}.issubset(metrics.columns)
    normal_metric = metrics.loc[metrics["anomaly_type"] == "normal"].iloc[0]
    assert 0.0 <= normal_metric["false_positive_rate"] <= 1.0


def test_pattern_rules_detect_structured_synthetic_changes():
    _, metrics = evaluate_synthetic_test(_normal_frame(1200), anomaly_length=30, seed=42, n_estimators=50)
    recalls = metrics.set_index("anomaly_type")["recall"]
    assert recalls["gradual_increase"] > 0.0
    assert recalls["std_increase"] > 0.0
    assert recalls["repeated_spike"] > 0.0
