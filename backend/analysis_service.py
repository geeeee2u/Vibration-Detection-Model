"""Run the existing detector with dashboard settings."""
from __future__ import annotations
from pathlib import Path
from backend.config import ModelSettings
from case1_vibration_isolation_forest import detect_anomalies, load_case1

def rerun_analysis(settings: ModelSettings, input_path: str | Path, output_path: str | Path):
    result = detect_anomalies(load_case1(input_path), **settings.__dict__)
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    result.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(target)
    return result
