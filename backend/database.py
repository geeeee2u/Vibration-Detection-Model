"""PostgreSQL persistence for dashboard source data, model runs, and settings."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine, make_url

from backend.config import ModelSettings


METADATA = MetaData()

RAW_VIBRATION_RECORDS = Table(
    "raw_vibration_records",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("source_case", String(100), nullable=False),
    Column("sampled_at", DateTime, nullable=False),
    Column("vibration", Float, nullable=False),
    UniqueConstraint("source_case", "sampled_at", name="uq_raw_vibration_case_timestamp"),
)

ANALYSIS_RUNS = Table(
    "analysis_runs",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("is_active", Boolean, nullable=False, server_default="false"),
)

ANALYSIS_RESULTS = Table(
    "analysis_results",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("run_id", BigInteger, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
    Column("row_order", Integer, nullable=False),
    Column("sampled_at", DateTime, nullable=False),
    Column("payload", JSONB, nullable=False),
    UniqueConstraint("run_id", "row_order", name="uq_analysis_result_run_row"),
)

PERFORMANCE_METRICS = Table(
    "performance_metrics",
    METADATA,
    Column("id", BigInteger, primary_key=True),
    Column("run_id", BigInteger, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
    Column("row_order", Integer, nullable=False),
    Column("payload", JSONB, nullable=False),
    UniqueConstraint("run_id", "row_order", name="uq_performance_metric_run_row"),
)

MODEL_SETTINGS = Table(
    "model_settings",
    METADATA,
    Column("singleton_id", Integer, primary_key=True),
    Column("payload", JSONB, nullable=False),
    Column("updated_at", DateTime, nullable=False, server_default=func.now(), onupdate=func.now()),
)


def _timestamp(value: Any) -> datetime:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("Timestamps cannot contain missing values")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


def _json_value(value: Any) -> Any:
    """Convert supported pandas values while rejecting non-persistable objects."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise TypeError(f"Unsupported value for PostgreSQL JSON payload: {type(value).__name__}")


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): _json_value(value) for key, value in record.items()} for record in frame.to_dict("records")]


class DatabaseRepository:
    """SQLAlchemy 2 repository backed exclusively by PostgreSQL."""

    def __init__(self, database_url: str):
        if not make_url(database_url).drivername.startswith("postgresql"):
            raise ValueError("DatabaseRepository requires a PostgreSQL database URL")
        self._engine: Engine = create_engine(database_url, pool_pre_ping=True)

    def create_schema(self) -> None:
        METADATA.create_all(self._engine)

    def import_raw_data(self, frame: pd.DataFrame, source_case: str) -> int:
        required_columns = {"Timestamps", "Vibration"}
        missing_columns = required_columns.difference(frame.columns)
        if missing_columns:
            raise ValueError(f"Raw data is missing required columns: {sorted(missing_columns)}")

        rows = [
            {
                "source_case": source_case,
                "sampled_at": _timestamp(row["Timestamps"]),
                "vibration": float(row["Vibration"]),
            }
            for row in frame[["Timestamps", "Vibration"]].to_dict("records")
        ]
        if not rows:
            return 0

        statement = insert(RAW_VIBRATION_RECORDS).values(rows).on_conflict_do_nothing(
            constraint="uq_raw_vibration_case_timestamp"
        )
        with self._engine.begin() as connection:
            result = connection.execute(statement)
        return int(result.rowcount or 0)

    def load_raw_data(self, source_case: str) -> pd.DataFrame:
        statement = (
            select(RAW_VIBRATION_RECORDS.c.sampled_at, RAW_VIBRATION_RECORDS.c.vibration)
            .where(RAW_VIBRATION_RECORDS.c.source_case == source_case)
            .order_by(RAW_VIBRATION_RECORDS.c.sampled_at)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return pd.DataFrame(
            [{"Timestamps": row["sampled_at"], "Vibration": float(row["vibration"])} for row in rows],
            columns=["Timestamps", "Vibration"],
        )

    def load_active_results(self) -> pd.DataFrame:
        return self._load_active_payloads(ANALYSIS_RESULTS, include_timestamp=True)

    def load_active_metrics(self) -> pd.DataFrame:
        return self._load_active_payloads(PERFORMANCE_METRICS, include_timestamp=False)

    def load_settings(self) -> ModelSettings:
        with self._engine.connect() as connection:
            payload = connection.execute(
                select(MODEL_SETTINGS.c.payload).where(MODEL_SETTINGS.c.singleton_id == 1)
            ).scalar_one_or_none()
        return ModelSettings(**payload) if payload is not None else ModelSettings()

    def save_settings(self, settings: ModelSettings) -> ModelSettings:
        with self._engine.begin() as connection:
            self._save_settings(connection, settings)
        return settings

    def replace_active_run(
        self,
        result: pd.DataFrame,
        metrics: pd.DataFrame,
        settings: ModelSettings,
    ) -> None:
        if "Timestamps" not in result.columns:
            raise ValueError("Analysis result is missing required Timestamps column")

        result_records = _frame_records(result)
        metric_records = _frame_records(metrics)
        result_rows = [
            {"row_order": index, "sampled_at": _timestamp(record["Timestamps"]), "payload": record}
            for index, record in enumerate(result_records)
        ]
        metric_rows = [
            {"row_order": index, "payload": record}
            for index, record in enumerate(metric_records)
        ]

        with self._engine.begin() as connection:
            run_id = connection.execute(
                insert(ANALYSIS_RUNS).values(is_active=False).returning(ANALYSIS_RUNS.c.id)
            ).scalar_one()
            if result_rows:
                connection.execute(
                    insert(ANALYSIS_RESULTS),
                    [{"run_id": run_id, **row} for row in result_rows],
                )
            if metric_rows:
                connection.execute(
                    insert(PERFORMANCE_METRICS),
                    [{"run_id": run_id, **row} for row in metric_rows],
                )
            self._save_settings(connection, settings)
            connection.execute(update(ANALYSIS_RUNS).where(ANALYSIS_RUNS.c.is_active.is_(True)).values(is_active=False))
            self._activate_run(connection, run_id)

    @staticmethod
    def _activate_run(connection: Any, run_id: int) -> None:
        """Mark a fully persisted run active as the final transaction operation."""
        connection.execute(update(ANALYSIS_RUNS).where(ANALYSIS_RUNS.c.id == run_id).values(is_active=True))

    def _load_active_payloads(self, table: Table, include_timestamp: bool) -> pd.DataFrame:
        statement = (
            select(table.c.payload)
            .join(ANALYSIS_RUNS, table.c.run_id == ANALYSIS_RUNS.c.id)
            .where(ANALYSIS_RUNS.c.is_active.is_(True))
            .order_by(table.c.row_order)
        )
        with self._engine.connect() as connection:
            payloads = connection.execute(statement).scalars().all()
        frame = pd.DataFrame(payloads)
        if include_timestamp and "Timestamps" in frame.columns:
            frame["Timestamps"] = pd.to_datetime(frame["Timestamps"])
        return frame

    @staticmethod
    def _save_settings(connection: Any, settings: ModelSettings) -> None:
        statement = insert(MODEL_SETTINGS).values(singleton_id=1, payload=asdict(settings)).on_conflict_do_update(
            index_elements=[MODEL_SETTINGS.c.singleton_id],
            set_={"payload": asdict(settings), "updated_at": func.now()},
        )
        connection.execute(statement)
