import pytest

from backend.config import ModelSettings, load_settings, save_settings


def test_settings_round_trip(tmp_path):
    path = tmp_path / "model_settings.json"
    settings = ModelSettings(threshold_quantile=0.998, persistence_seconds=6)
    save_settings(settings, path)
    assert load_settings(path) == settings


def test_settings_rejects_invalid_window_order():
    with pytest.raises(ValueError):
        ModelSettings(short_window=61, long_window=60)
