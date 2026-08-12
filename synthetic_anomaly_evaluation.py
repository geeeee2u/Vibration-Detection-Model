"""Synthetic anomaly evaluation and line-plot generation for Case1."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from case1_vibration_isolation_forest import fit_detector, score_detector


ANOMALY_TYPES = [
    "gradual_increase",
    "increase_1_to_5pct",
    "std_increase",
    "repeated_spike",
    "independent_random",
]


def generate_synthetic_test(normal_df: pd.DataFrame, anomaly_length: int = 30, seed: int = 42) -> pd.DataFrame:
    """Copy normal data and inject labeled, non-overlapping anomaly windows."""
    if anomaly_length < 5:
        raise ValueError("anomaly_length must be at least 5")
    if len(normal_df) < (len(ANOMALY_TYPES) + 1) * anomaly_length:
        raise ValueError("normal_df is too short for all synthetic anomaly windows")

    rng = np.random.default_rng(seed)
    result = normal_df[["Timestamps", "Vibration"]].copy().reset_index(drop=True)
    result["injected_type"] = "normal"
    result["injected_anomaly"] = False
    baseline = float(result["Vibration"].median())
    scale = float(result["Vibration"].std())
    starts = np.linspace(len(result) // 10, len(result) - anomaly_length - 1, len(ANOMALY_TYPES), dtype=int)

    for anomaly_type, start in zip(ANOMALY_TYPES, starts):
        end = start + anomaly_length
        values = result.loc[start:end - 1, "Vibration"].to_numpy(dtype=float)
        local_start = max(0, start - 20)
        local_baseline = float(result.loc[local_start:start - 1, "Vibration"].median())
        local_scale = float(result.loc[local_start:start - 1, "Vibration"].std())
        local_scale = max(local_scale, 0.01)
        if anomaly_type == "gradual_increase":
            values = local_baseline + np.linspace(0.0, max(3.0, 8.0 * local_scale), anomaly_length)
        elif anomaly_type == "increase_1_to_5pct":
            values = values * 1.03
        elif anomaly_type == "std_increase":
            values = local_baseline + rng.normal(0.0, max(1.5, 8.0 * local_scale), anomaly_length)
        elif anomaly_type == "repeated_spike":
            values = np.full(anomaly_length, local_baseline)
            values[::5] = local_baseline + max(5.0, 20.0 * local_scale)
        elif anomaly_type == "independent_random":
            values = rng.uniform(baseline + 15.0 * max(scale, 0.01), baseline + 25.0 * max(scale, 0.01), anomaly_length)
        result.loc[start:end - 1, "Vibration"] = values
        result.loc[start:end - 1, "injected_type"] = anomaly_type
        result.loc[start:end - 1, "injected_anomaly"] = True
    return result


def evaluate_synthetic_test(
    normal_df: pd.DataFrame,
    anomaly_length: int = 30,
    seed: int = 42,
    threshold_quantile: float = 0.999,
    persistence_seconds: int = 5,
    n_estimators: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train only on normal_df, then evaluate on a labeled synthetic copy."""
    synthetic = generate_synthetic_test(normal_df, anomaly_length=anomaly_length, seed=seed)
    detector = fit_detector(normal_df, threshold_quantile=threshold_quantile, n_estimators=n_estimators, random_state=seed)
    scored = score_detector(detector, synthetic, persistence_seconds=persistence_seconds)
    scored["injected_type"] = synthetic["injected_type"]
    scored["injected_anomaly"] = synthetic["injected_anomaly"]

    rows = []
    for anomaly_type in ["normal"] + ANOMALY_TYPES:
        mask = scored["injected_type"] == anomaly_type
        actual = scored.loc[mask, "injected_anomaly"]
        predicted = scored.loc[mask, "confirmed_anomaly"]
        recall = float(predicted.mean()) if actual.any() else 0.0
        normal_mask = ~scored["injected_anomaly"]
        false_positive_rate = float(scored.loc[normal_mask, "confirmed_anomaly"].mean()) if anomaly_type == "normal" else 0.0
        rows.append({"anomaly_type": anomaly_type, "recall": recall, "false_positive_rate": false_positive_rate, "rows": int(mask.sum())})
    return scored, pd.DataFrame(rows)


def plot_synthetic_anomalies(normal_df: pd.DataFrame, output_path: str | Path, anomaly_length: int = 30, seed: int = 42) -> None:
    """Save a five-panel line plot showing each injected anomaly window."""
    synthetic = generate_synthetic_test(normal_df, anomaly_length=anomaly_length, seed=seed)
    fig, axes = plt.subplots(len(ANOMALY_TYPES), 1, figsize=(12, 13), sharey=False)
    for ax, anomaly_type in zip(axes, ANOMALY_TYPES):
        idx = synthetic.index[synthetic["injected_type"] == anomaly_type]
        start = max(0, int(idx.min()) - 20)
        end = min(len(synthetic), int(idx.max()) + 21)
        ax.plot(normal_df.loc[start:end - 1, "Vibration"].to_numpy(), label="Original normal", linewidth=1.2)
        ax.plot(synthetic.loc[start:end - 1, "Vibration"].to_numpy(), label="Synthetic test", linewidth=1.2)
        ax.axvspan(int(idx.min() - start), int(idx.max() - start), alpha=0.18, label="Injected anomaly")
        ax.set_title(anomaly_type)
        ax.set_ylabel("Vibration")
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left")
    axes[-1].set_xlabel("Relative sample index")
    fig.suptitle("Case1 synthetic anomaly test patterns", fontsize=14)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Case1 detector with synthetic anomalies")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="synthetic_anomaly_outputs")
    parser.add_argument("--threshold-quantile", type=float, default=0.999)
    parser.add_argument("--persistence-seconds", type=int, default=5)
    parser.add_argument("--n-estimators", type=int, default=300)
    args = parser.parse_args()

    from case1_vibration_isolation_forest import load_case1

    normal = load_case1(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scored, metrics = evaluate_synthetic_test(
        normal,
        threshold_quantile=args.threshold_quantile,
        persistence_seconds=args.persistence_seconds,
        n_estimators=args.n_estimators,
    )
    scored.to_csv(output_dir / "synthetic_anomaly_scored.csv", index=False, encoding="utf-8-sig")
    metrics.to_csv(output_dir / "synthetic_anomaly_metrics.csv", index=False, encoding="utf-8-sig")
    plot_synthetic_anomalies(normal, output_dir / "synthetic_anomaly_patterns.png")
    print(metrics.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
