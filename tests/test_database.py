"""Integration tests for PostgreSQL dashboard persistence.

Set TEST_DATABASE_URL to a disposable PostgreSQL database to run these tests.
"""

from __future__ import annotations

import os
import uuid

import pandas as pd
import pytest


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def repository():
    """Return an empty repository backed by the explicitly configured test DB."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")

    from backend.database import DatabaseRepository

    repository = DatabaseRepository(TEST_DATABASE_URL)
    repository.create_schema()
    return repository


def test_import_raw_data_is_idempotent(repository):
    """Repeating a Case1 import must not duplicate records with the same timestamp."""
    # A missing unique Case/timestamp constraint would make this test fail.
    source_case = f"Case1-test-{uuid.uuid4()}"
    frame = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-01 00:00:02", "2026-01-01 00:00:01"]),
            "Vibration": [2.0, 1.0],
        }
    )

    assert repository.import_raw_data(frame, source_case) == 2
    assert repository.import_raw_data(frame, source_case) == 0

    loaded = repository.load_raw_data(source_case)
    assert loaded["Timestamps"].tolist() == [pd.Timestamp("2026-01-01 00:00:01"), pd.Timestamp("2026-01-01 00:00:02")]
    assert loaded["Vibration"].tolist() == [1.0, 2.0]


def test_active_results_and_metrics_persist(repository):
    """The active run must expose all result fields and synthetic metric rows."""
    # Dropping JSON result payloads or failing to activate the new run breaks this test.
    from backend.config import ModelSettings

    timestamps = pd.to_datetime(["2026-01-01 00:00:01", "2026-01-01 00:00:02"])
    result = pd.DataFrame(
        {
            "Timestamps": timestamps,
            "Vibration": [1.0, 1.5],
            "short_mean": [1.0, 1.25],
            "anomaly_score": [0.1, 0.9],
            "threshold": [0.8, 0.8],
            "raw_anomaly": [False, True],
            "confirmed_anomaly": [False, True],
            "is_anomaly": [False, True],
            "anomaly_type": ["normal", "repeated_spike"],
        }
    )
    metrics = pd.DataFrame(
        [
            {"anomaly_type": "normal", "recall": 0.0, "false_positive_rate": 0.003, "rows": 100},
            {"anomaly_type": "repeated_spike", "recall": 1.0, "false_positive_rate": 0.0, "rows": 30},
        ]
    )

    repository.replace_active_run(result, metrics, ModelSettings(persistence_seconds=6))

    loaded_result = repository.load_active_results()
    loaded_metrics = repository.load_active_metrics()
    assert loaded_result["anomaly_type"].tolist() == ["normal", "repeated_spike"]
    assert loaded_result["confirmed_anomaly"].tolist() == [False, True]
    assert loaded_result["Timestamps"].tolist() == list(timestamps)
    assert loaded_metrics.to_dict("records") == metrics.to_dict("records")


def test_settings_round_trip(repository):
    """Saving model controls must make the same validated settings available later."""
    # Ignoring a persisted field would make the loaded dataclass differ.
    from backend.config import ModelSettings

    settings = ModelSettings(threshold_quantile=0.998, persistence_seconds=7, n_estimators=500)

    assert repository.save_settings(settings) == settings
    assert repository.load_settings() == settings


def test_failed_active_run_replacement_keeps_previous_active_run(repository):
    """A failed replacement must leave the previously published results available."""
    # Deactivating the prior run before the transaction succeeds would make this fail.
    from backend.config import ModelSettings

    original = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-01 00:00:01"]),
            "Vibration": [1.0],
            "is_anomaly": [False],
        }
    )
    metrics = pd.DataFrame(
        [{"anomaly_type": "normal", "recall": 0.0, "false_positive_rate": 0.003, "rows": 1}]
    )
    repository.replace_active_run(original, metrics, ModelSettings())

    invalid = original.assign(Vibration=[object()])
    with pytest.raises(TypeError):
        repository.replace_active_run(invalid, metrics, ModelSettings(persistence_seconds=6))

    assert repository.load_active_results()["Vibration"].tolist() == [1.0]


def test_final_activation_failure_rolls_back_to_previous_active_run(repository, monkeypatch):
    """A SQL failure during final activation must keep the previously active run visible."""
    # Removing the transaction boundary or committing the deactivation first would make this fail.
    from backend.config import ModelSettings
    from backend.database import ANALYSIS_RUNS
    from sqlalchemy.engine import Connection

    original = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-02 00:00:01"]),
            "Vibration": [1.0],
            "is_anomaly": [False],
        }
    )
    replacement = pd.DataFrame(
        {
            "Timestamps": pd.to_datetime(["2026-01-02 00:00:02"]),
            "Vibration": [9.0],
            "is_anomaly": [True],
        }
    )
    metrics = pd.DataFrame(
        [{"anomaly_type": "normal", "recall": 0.0, "false_positive_rate": 0.003, "rows": 1}]
    )
    repository.replace_active_run(original, metrics, ModelSettings())

    original_execute = Connection.execute
    activation_execute_attempted = False

    def fail_final_activation_execute(connection, statement, parameters=None, *, execution_options=None):
        nonlocal activation_execute_attempted
        is_final_activation = (
            getattr(statement, "is_update", False)
            and statement.table is ANALYSIS_RUNS
            and "analysis_runs.id" in str(statement)
        )
        if connection.engine is repository._engine and is_final_activation:
            activation_execute_attempted = True
            raise RuntimeError("simulated final activation SQL failure")
        return original_execute(connection, statement, parameters, execution_options=execution_options)

    monkeypatch.setattr(Connection, "execute", fail_final_activation_execute)
    with pytest.raises(RuntimeError, match="simulated final activation SQL failure"):
        repository.replace_active_run(replacement, metrics, ModelSettings(persistence_seconds=6))

    assert activation_execute_attempted
    assert repository.load_active_results()["Vibration"].tolist() == [1.0]
