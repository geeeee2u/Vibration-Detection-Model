"""Validated local settings for Case1 model reanalysis."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSettings:
    threshold_quantile: float = 0.999
    persistence_seconds: int = 5
    n_estimators: int = 300
    random_state: int = 42
    short_window: int = 15
    long_window: int = 60
    slope_window: int = 30

    def __post_init__(self) -> None:
        if not 0.5 < self.threshold_quantile < 1.0:
            raise ValueError("threshold_quantile must be between 0.5 and 1.0")
        if self.persistence_seconds < 1 or self.n_estimators < 1:
            raise ValueError("persistence_seconds and n_estimators must be positive")
        if not 0 < self.short_window <= self.long_window or self.slope_window < 2:
            raise ValueError("window values are inconsistent")


def load_settings(path: str | Path) -> ModelSettings:
    settings_path = Path(path)
    if not settings_path.exists():
        return ModelSettings()
    return ModelSettings(**json.loads(settings_path.read_text(encoding="utf-8")))


def save_settings(settings: ModelSettings, path: str | Path) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = settings_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(settings_path)
