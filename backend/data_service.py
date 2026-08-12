"""Read Case1 analysis output and shape it for dashboard pages."""
from __future__ import annotations

from pathlib import Path
import pandas as pd

BOOL_COLUMNS = ["raw_anomaly", "confirmed_anomaly", "is_anomaly"]

def load_results(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["Timestamps"])
    for column in BOOL_COLUMNS:
        if column in frame:
            frame[column] = frame[column].astype(str).str.lower().isin(["true", "1"])
    return frame.sort_values("Timestamps").reset_index(drop=True)

def filter_results(frame: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    result = frame
    if start:
        result = result[result["Timestamps"] >= pd.Timestamp(start)]
    if end:
        result = result[result["Timestamps"] <= pd.Timestamp(end)]
    return result.copy()

def _record(row: pd.Series) -> dict:
    data = row.to_dict()
    data["Timestamps"] = pd.Timestamp(data["Timestamps"]).isoformat()
    for key, value in list(data.items()):
        if hasattr(value, "item"):
            data[key] = value.item()
    return data

def overview_payload(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"latest": None, "confirmed_alarm_count": 0, "raw_candidate_count": 0, "normal_mean": None, "anomaly_mean": None, "type_breakdown": {}}
    latest = _record(frame.iloc[-1])
    latest["status"] = "confirmed_anomaly" if latest["confirmed_anomaly"] else "raw_candidate" if latest["raw_anomaly"] else "normal"
    confirmed = frame[frame["is_anomaly"]]
    normal = frame[~frame["is_anomaly"]]
    return {"latest": latest, "confirmed_alarm_count": int(frame["is_anomaly"].sum()), "raw_candidate_count": int(frame["raw_anomaly"].sum()), "normal_mean": float(normal["Vibration"].mean()) if not normal.empty else None, "anomaly_mean": float(confirmed["Vibration"].mean()) if not confirmed.empty else None, "type_breakdown": {str(k): int(v) for k, v in confirmed["anomaly_type"].value_counts().items()}}

def rows_payload(frame: pd.DataFrame, columns: list[str] | None = None) -> list[dict]:
    if columns:
        frame = frame[[column for column in columns if column in frame]]
    return [_record(row) for _, row in frame.iterrows()]
