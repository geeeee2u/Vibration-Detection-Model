"""Run the existing detector with dashboard settings."""
from __future__ import annotations
from pathlib import Path
from backend.config import ModelSettings
from backend.database import DatabaseRepository
from case1_vibration_isolation_forest import detect_anomalies, load_case1
from synthetic_anomaly_evaluation import evaluate_synthetic_test

def _write_temporary_csv(frame, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    return temporary


def rerun_analysis(
    settings: ModelSettings,
    input_path: str | Path,
    output_path: str | Path,
    metrics_path: str | Path,
):
    normal_data = load_case1(input_path)
    result = detect_anomalies(normal_data, **settings.__dict__)
    _, metrics = evaluate_synthetic_test(
        normal_data,
        threshold_quantile=settings.threshold_quantile,
        persistence_seconds=settings.persistence_seconds,
        n_estimators=settings.n_estimators,
        seed=settings.random_state,
    )

    result_temporary = None
    metrics_temporary = None
    try:
        result_temporary = _write_temporary_csv(result, output_path)
        metrics_temporary = _write_temporary_csv(metrics, metrics_path)
        result_temporary.replace(Path(output_path))
        metrics_temporary.replace(Path(metrics_path))
    finally:
        for temporary in (result_temporary, metrics_temporary):
            if temporary and temporary.exists():
                temporary.unlink()
    return result


def rerun_analysis_from_repository(
    settings: ModelSettings,
    repository: DatabaseRepository,
    source_case: str = "Case1",
):
    """Analyze persisted raw data and atomically publish a new active run."""
    normal_data = repository.load_raw_data(source_case)
    if normal_data.empty:
        raise ValueError(f"No raw vibration data found for source case: {source_case}")

    result = detect_anomalies(normal_data, **settings.__dict__)
    _, metrics = evaluate_synthetic_test(
        normal_data,
        threshold_quantile=settings.threshold_quantile,
        persistence_seconds=settings.persistence_seconds,
        n_estimators=settings.n_estimators,
        seed=settings.random_state,
    )
    repository.replace_active_run(result, metrics, settings)
    return result
