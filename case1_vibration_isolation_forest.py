"""Isolation Forest anomaly detection for Case1 Vibration data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


FEATURE_COLUMNS = [
    "short_mean",
    "short_std",
    "long_mean",
    "long_std",
    "diff_abs",
    "mean_gap",
    "slope",
    "short_pct_change",
    "volatility_ratio",
    "spike_count",
]


@dataclass
class DetectorBundle:
    model: IsolationForest
    score_threshold: float
    pattern_thresholds: dict[str, float]


def _rolling_slope(values: pd.Series, window: int) -> pd.Series:
    """Return the least-squares slope in each trailing window."""
    x = np.arange(window, dtype=float)

    def slope(window_values: np.ndarray) -> float:
        y = np.asarray(window_values, dtype=float)
        if len(y) < 2 or not np.isfinite(y).all():
            return 0.0
        x_window = x[-len(y):]
        x_centered = x_window - x_window.mean()
        denominator = float(np.dot(x_centered, x_centered))
        if denominator == 0:
            return 0.0
        return float(np.dot(x_centered, y - y.mean()) / denominator)

    return values.rolling(window=window, min_periods=2).apply(slope, raw=True).fillna(0.0)


def build_features(
    df: pd.DataFrame,
    short_window: int = 15,
    long_window: int = 60,
    slope_window: int = 30,
    spike_level: float | None = None,
) -> pd.DataFrame:
    """Create explainable rolling features from Case1 Vibration values."""
    if not (0 < short_window <= long_window and slope_window > 1):
        raise ValueError("Require 0 < short_window <= long_window and slope_window > 1")
    if "Vibration" not in df.columns:
        raise ValueError("Input data must contain a Vibration column")

    result = df.copy().reset_index(drop=True)
    vibration = pd.to_numeric(result["Vibration"], errors="coerce")
    if vibration.isna().all():
        raise ValueError("Vibration contains no numeric values")
    vibration = vibration.interpolate(limit_direction="both")
    result["Vibration"] = vibration

    short = vibration.rolling(short_window, min_periods=1)
    long = vibration.rolling(long_window, min_periods=1)
    result["short_mean"] = short.mean()
    result["short_std"] = short.std(ddof=0)
    result["long_mean"] = long.mean()
    result["long_std"] = long.std(ddof=0)
    result["diff_abs"] = vibration.diff().abs().fillna(0.0)
    result["mean_gap"] = result["short_mean"] - result["long_mean"]
    result["slope"] = _rolling_slope(vibration, slope_window)
    result["short_pct_change"] = result["mean_gap"] / result["long_mean"].abs().clip(lower=1e-9)
    result["volatility_ratio"] = (result["short_std"] + 1e-9) / (result["long_std"] + 1e-9)
    if spike_level is None:
        spike_level = float(result["diff_abs"].quantile(0.999))
    spike_event = result["diff_abs"] >= max(float(spike_level), 1e-9)
    result["spike_count"] = spike_event.astype(float).rolling(max(short_window, 30), min_periods=1).sum()
    result[FEATURE_COLUMNS] = result[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return result


def classify_anomalies(result_df: pd.DataFrame) -> pd.DataFrame:
    """Assign a human-readable type to Isolation Forest anomaly rows."""
    result = result_df.copy()
    required = {"is_anomaly", "short_mean", "long_mean", "short_std", "long_std", "diff_abs", "slope"}
    missing = required.difference(result.columns)
    if missing:
        raise ValueError(f"Missing columns for classification: {sorted(missing)}")

    result["anomaly_type"] = "normal"
    if "pattern_type" in result.columns:
        result.loc[result["is_anomaly"], "anomaly_type"] = result.loc[result["is_anomaly"], "pattern_type"]
        result.loc[result["is_anomaly"] & (result["anomaly_type"] == "normal"), "anomaly_type"] = "general_anomaly"
        return result
    anomalous = result["is_anomaly"].astype(bool)
    baseline = result["long_mean"].abs().clip(lower=1e-9)
    mean_ratio = result["short_mean"] / baseline - 1.0
    std_ratio = result["short_std"] / result["long_std"].abs().clip(lower=1e-9)
    diff_baseline = result["diff_abs"].rolling(60, min_periods=5).median().fillna(result["diff_abs"].median())

    gradual = anomalous & (result["slope"] > 0) & (result["mean_gap"] > 0)
    increase = anomalous & mean_ratio.between(0.01, 0.05, inclusive="both")
    std_increase = anomalous & (std_ratio > 1.25)
    repeated_spike = anomalous & (result["diff_abs"] > (3.0 * diff_baseline.clip(lower=1e-9)))

    result.loc[gradual, "anomaly_type"] = "gradual_increase"
    result.loc[increase & ~gradual, "anomaly_type"] = "increase_1_to_5pct"
    result.loc[std_increase & ~(gradual | increase), "anomaly_type"] = "std_increase"
    result.loc[repeated_spike & ~(gradual | increase | std_increase), "anomaly_type"] = "repeated_spike"
    result.loc[anomalous & (result["anomaly_type"] == "normal"), "anomaly_type"] = "general_anomaly"
    return result


def confirm_persistent_anomalies(raw_anomalies: pd.Series, min_consecutive: int = 5) -> pd.Series:
    """Keep only anomaly runs lasting at least ``min_consecutive`` rows."""
    if min_consecutive < 1:
        raise ValueError("min_consecutive must be at least 1")
    raw = raw_anomalies.astype(bool)
    groups = raw.ne(raw.shift(fill_value=False)).cumsum()
    run_lengths = raw.groupby(groups).transform("sum")
    return raw & (run_lengths >= min_consecutive)


def detect_anomalies(
    df: pd.DataFrame,
    threshold_quantile: float = 0.999,
    n_estimators: int = 300,
    random_state: int = 42,
    short_window: int = 15,
    long_window: int = 60,
    slope_window: int = 30,
    persistence_seconds: int = 5,
) -> pd.DataFrame:
    """Fit Isolation Forest and flag scores above a normal-data threshold."""
    if not 0.5 < threshold_quantile < 1.0:
        raise ValueError("threshold_quantile must be between 0.5 and 1.0")
    if persistence_seconds < 1:
        raise ValueError("persistence_seconds must be at least 1")
    detector = fit_detector(
        df,
        threshold_quantile=threshold_quantile,
        n_estimators=n_estimators,
        random_state=random_state,
        short_window=short_window,
        long_window=long_window,
        slope_window=slope_window,
    )
    return score_detector(
        detector,
        df,
        short_window=short_window,
        long_window=long_window,
        slope_window=slope_window,
        persistence_seconds=persistence_seconds,
    )


def fit_detector(
    normal_df: pd.DataFrame,
    threshold_quantile: float = 0.999,
    n_estimators: int = 300,
    random_state: int = 42,
    short_window: int = 15,
    long_window: int = 60,
    slope_window: int = 30,
) -> DetectorBundle:
    """Fit on normal data and learn a score threshold from that same normal data."""
    if not 0.5 < threshold_quantile < 1.0:
        raise ValueError("threshold_quantile must be between 0.5 and 1.0")
    normal_vibration = pd.to_numeric(normal_df["Vibration"], errors="coerce").dropna()
    spike_level = float(normal_vibration.diff().abs().quantile(0.999))
    features = build_features(normal_df, short_window, long_window, slope_window, spike_level=spike_level)
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination="auto",
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(features[FEATURE_COLUMNS])
    normal_scores = -model.decision_function(features[FEATURE_COLUMNS])
    threshold = float(pd.Series(normal_scores).quantile(threshold_quantile))
    positive_slopes = features["slope"].clip(lower=0)
    positive_changes = features["short_pct_change"].clip(lower=0)
    pattern_thresholds = {
        "slope": max(0.01, float(positive_slopes.quantile(0.999))),
        "short_pct_change": max(0.01, float(positive_changes.quantile(0.999))),
        "volatility_ratio": max(1.25, float(features["volatility_ratio"].quantile(0.999))),
        "spike_count": max(3.0, float(np.ceil(features["spike_count"].quantile(0.999)))),
        "spike_level": spike_level,
    }
    return DetectorBundle(model=model, score_threshold=threshold, pattern_thresholds=pattern_thresholds)


def score_detector(
    detector: DetectorBundle,
    df: pd.DataFrame,
    short_window: int = 15,
    long_window: int = 60,
    slope_window: int = 30,
    persistence_seconds: int = 5,
) -> pd.DataFrame:
    """Score new data with a fitted detector and apply persistence confirmation."""
    if persistence_seconds < 1:
        raise ValueError("persistence_seconds must be at least 1")
    features = build_features(
        df,
        short_window,
        long_window,
        slope_window,
        spike_level=detector.pattern_thresholds["spike_level"],
    )
    features["anomaly_score"] = -detector.model.decision_function(features[FEATURE_COLUMNS])
    features["threshold"] = detector.score_threshold
    score_candidate = features["anomaly_score"] >= detector.score_threshold
    pattern_type = pd.Series("normal", index=features.index, dtype="object")
    gradual = (features["slope"] >= detector.pattern_thresholds["slope"]) & (features["short_pct_change"] >= 0.01)
    increase = features["short_pct_change"].between(detector.pattern_thresholds["short_pct_change"], 0.05, inclusive="both")
    std_increase = features["volatility_ratio"] >= detector.pattern_thresholds["volatility_ratio"]
    repeated_spike = features["spike_count"] >= detector.pattern_thresholds["spike_count"]
    pattern_type.loc[gradual] = "gradual_increase"
    pattern_type.loc[increase & (pattern_type == "normal")] = "increase_1_to_5pct"
    pattern_type.loc[std_increase & (pattern_type == "normal")] = "std_increase"
    pattern_type.loc[repeated_spike & (pattern_type == "normal")] = "repeated_spike"
    pattern_candidate = pattern_type != "normal"
    features["pattern_type"] = pattern_type
    features["raw_anomaly"] = (score_candidate | pattern_candidate).astype(bool)
    features["confirmed_anomaly"] = confirm_persistent_anomalies(features["raw_anomaly"], persistence_seconds)
    features["is_anomaly"] = features["confirmed_anomaly"]
    return classify_anomalies(features)


def load_case1(input_path: str | Path) -> pd.DataFrame:
    """Load and validate only Case1 Timestamps and Vibration columns."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    try:
        frame = pd.read_excel(path, sheet_name="Case1")
    except ValueError as exc:
        raise ValueError("Case1 sheet must contain Timestamps and Vibration columns") from exc
    required = {"Timestamps", "Vibration"}
    if not required.issubset(frame.columns):
        raise ValueError("Case1 input must contain Timestamps and Vibration columns")
    frame = frame[["Timestamps", "Vibration"]].copy()
    frame["Timestamps"] = pd.to_datetime(frame["Timestamps"], errors="coerce")
    frame["Vibration"] = pd.to_numeric(frame["Vibration"], errors="coerce")
    frame = frame.dropna(subset=["Timestamps", "Vibration"])
    frame = frame.sort_values("Timestamps").drop_duplicates("Timestamps", keep="first").reset_index(drop=True)
    if frame.empty:
        raise ValueError("Case1 contains no valid Timestamps/Vibration rows")
    return frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect Case1 Vibration anomalies with Isolation Forest")
    parser.add_argument("--input", required=True, help="Path to AI Model Raw Data.xlsx")
    parser.add_argument("--output", default="case1_vibration_anomaly_results.csv", help="Output CSV path")
    parser.add_argument("--threshold-quantile", type=float, default=0.999, help="Normal-score quantile used as anomaly threshold")
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--short-window", type=int, default=15)
    parser.add_argument("--long-window", type=int, default=60)
    parser.add_argument("--slope-window", type=int, default=30)
    parser.add_argument("--persistence-seconds", type=int, default=5, help="Consecutive raw anomalies required for confirmation")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data = load_case1(args.input)
    result = detect_anomalies(
        data,
        threshold_quantile=args.threshold_quantile,
        n_estimators=args.n_estimators,
        random_state=args.random_state,
        short_window=args.short_window,
        long_window=args.long_window,
        slope_window=args.slope_window,
        persistence_seconds=args.persistence_seconds,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved {len(result):,} rows to {output_path}")
    print(result["anomaly_type"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
