from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from case1_vibration_isolation_forest import (
    build_features,
    confirm_persistent_anomalies,
    detect_anomalies,
    load_case1,
)


class Case1VibrationTests(unittest.TestCase):
    def test_build_features_returns_expected_columns_and_no_nan_rows(self):
        frame = pd.DataFrame(
            {
                "Timestamps": pd.date_range("2026-01-01", periods=20, freq="s"),
                "Vibration": np.linspace(1.0, 2.0, 20),
            }
        )
        features = build_features(frame, short_window=3, long_window=7, slope_window=5)
        expected = {
            "short_mean", "short_std", "long_mean", "long_std", "diff_abs", "mean_gap", "slope",
            "short_pct_change", "volatility_ratio", "spike_count",
        }
        self.assertTrue(expected.issubset(features.columns))
        self.assertEqual(len(features), 20)
        self.assertTrue(features[list(expected)].notna().all().all())

    def test_detect_anomalies_marks_a_large_spike(self):
        values = np.ones(80)
        values[60] = 8.0
        frame = pd.DataFrame(
            {
                "Timestamps": pd.date_range("2026-01-01", periods=80, freq="s"),
                "Vibration": values,
            }
        )
        result = detect_anomalies(
            frame, threshold_quantile=0.95, n_estimators=100, random_state=42, persistence_seconds=1,
            short_window=5, long_window=15, slope_window=7,
        )
        self.assertTrue(bool(result.loc[60, "is_anomaly"]))
        self.assertEqual(result.loc[0, "anomaly_type"], "normal")

    def test_classification_can_identify_increased_variability(self):
        values = np.r_[np.ones(50), np.tile([0.5, 1.5], 15)]
        frame = pd.DataFrame(
            {
                "Timestamps": pd.date_range("2026-01-01", periods=len(values), freq="s"),
                "Vibration": values,
            }
        )
        result = detect_anomalies(
            frame, threshold_quantile=0.90, n_estimators=100, random_state=42, persistence_seconds=1,
            short_window=5, long_window=15, slope_window=7,
        )
        self.assertIn("std_increase", set(result.loc[result["is_anomaly"], "anomaly_type"]))

    def test_load_case1_requires_case1_vibration_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            bad_path = Path(directory) / "bad.xlsx"
            pd.DataFrame({"wrong": [1]}).to_excel(bad_path, index=False)
            with self.assertRaisesRegex(ValueError, "Case1.*Vibration"):
                load_case1(bad_path)

    def test_real_workbook_case1_smoke(self):
        path = Path(__file__).parents[1] / "AI Model Raw Data.xlsx"
        result = detect_anomalies(
            load_case1(path), threshold_quantile=0.99, n_estimators=50, random_state=42,
            short_window=15, long_window=60, slope_window=30,
        )
        self.assertEqual(len(result), 93214)
        self.assertEqual(result["is_anomaly"].dtype, bool)
        self.assertTrue(result["anomaly_type"].notna().all())

    def test_threshold_is_learned_from_normal_scores(self):
        rng = np.random.default_rng(42)
        values = 3.3 + rng.normal(0, 0.02, 1000)
        frame = pd.DataFrame(
            {
                "Timestamps": pd.date_range("2026-01-01", periods=1000, freq="s"),
                "Vibration": values,
            }
        )
        result = detect_anomalies(
            frame,
            threshold_quantile=0.999,
            n_estimators=100,
            random_state=42,
            short_window=15,
            long_window=60,
            slope_window=30,
        )
        self.assertIn("threshold", result.columns)
        self.assertEqual(result["threshold"].nunique(), 1)
        self.assertLessEqual(int(result["is_anomaly"].sum()), 5)

    def test_only_consecutive_raw_anomalies_are_confirmed(self):
        raw = pd.Series([False, True, False, True, True, True, True, True, False])
        confirmed = confirm_persistent_anomalies(raw, min_consecutive=5)
        self.assertEqual(confirmed.tolist(), [False, False, False, True, True, True, True, True, False])


if __name__ == "__main__":
    unittest.main()
