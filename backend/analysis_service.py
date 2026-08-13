"""Run the existing detector with dashboard settings."""
from __future__ import annotations
from pathlib import Path
from backend.config import ModelSettings
from case1_vibration_isolation_forest import detect_anomalies, load_case1
from synthetic_anomaly_evaluation import evaluate_synthetic_test

def _write_csv(frame, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(target)


def rerun_analysis(
    settings: ModelSettings,
    input_path: str | Path,
    output_path: str | Path,
    metrics_path: str | Path,
):
    normal_data = load_case1(input_path)
    result = detect_anomalies(normal_data, **settings.__dict__)
    _write_csv(result, output_path)

    _, metrics = evaluate_synthetic_test(
        normal_data,
        threshold_quantile=settings.threshold_quantile,
        persistence_seconds=settings.persistence_seconds,
        n_estimators=settings.n_estimators,
        seed=settings.random_state,
    )
    _write_csv(metrics, metrics_path)
    return result
