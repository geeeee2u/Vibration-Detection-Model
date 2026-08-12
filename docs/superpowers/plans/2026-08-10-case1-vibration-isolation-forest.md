# Case1 Vibration Isolation Forest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Python script that reads Case1 `Vibration` data, detects anomalies with Isolation Forest, classifies anomaly patterns, and writes CSV results.

**Architecture:** Keep data loading, feature engineering, anomaly classification, and CLI execution as small functions in one focused script. Use a separate pytest file for deterministic unit tests with synthetic time series; use the real workbook only for an integration smoke test.

**Tech Stack:** Python 3, pandas, numpy, scikit-learn, pytest.

## Global Constraints

- Use only the `Case1` sheet and its `Vibration` column as the signal.
- Treat the workbook as unlabeled for training because `구분` contains only `정상`.
- Default `contamination=0.01`, `n_estimators=300`, and fixed `random_state=42`.
- Output one row per valid input observation, with score, flag, and anomaly type.
- Do not overwrite the source workbook.

---

### Task 1: Define testable data and feature interfaces

**Files:**
- Create: `tests/test_case1_vibration_isolation_forest.py`
- Create: `case1_vibration_isolation_forest.py`

**Interfaces:**
- `build_features(df, short_window, long_window, slope_window) -> pandas.DataFrame`
- `classify_anomalies(result_df) -> pandas.DataFrame`
- `detect_anomalies(df, contamination, n_estimators, random_state, short_window, long_window, slope_window) -> pandas.DataFrame`

- [ ] **Step 1: Write the failing test for feature columns and aligned rows**

```python
import numpy as np
import pandas as pd

from case1_vibration_isolation_forest import build_features


def test_build_features_returns_expected_columns_and_no_nan_rows():
    frame = pd.DataFrame({"Timestamps": pd.date_range("2026-01-01", periods=20, freq="s"), "Vibration": np.linspace(1.0, 2.0, 20)})
    features = build_features(frame, short_window=3, long_window=7, slope_window=5)
    assert {"short_mean", "short_std", "long_mean", "long_std", "diff_abs", "mean_gap", "slope"}.issubset(features.columns)
    assert len(features) == 20
    assert features[["short_mean", "short_std", "long_mean", "long_std", "diff_abs", "mean_gap", "slope"]].notna().all().all()
```

- [ ] **Step 2: Run the test to verify it fails because the module is absent**

Run: `pytest -q tests/test_case1_vibration_isolation_forest.py::test_build_features_returns_expected_columns_and_no_nan_rows`

Expected: FAIL with `ModuleNotFoundError` for `case1_vibration_isolation_forest`.

- [ ] **Step 3: Implement the minimal feature builder**

Create `build_features` that coerces `Vibration` to numeric, computes centered-safe rolling statistics with `min_periods=1`, computes `diff_abs`, `mean_gap`, and a rolling least-squares slope, then backfills/forward-fills only feature warm-up gaps. Preserve `Timestamps` and `Vibration`.

- [ ] **Step 4: Run the focused test and confirm it passes**

Run: `pytest -q tests/test_case1_vibration_isolation_forest.py::test_build_features_returns_expected_columns_and_no_nan_rows`

Expected: PASS.

- [ ] **Step 5: Commit if a Git repository is initialized**

Run: `git add case1_vibration_isolation_forest.py tests/test_case1_vibration_isolation_forest.py && git commit -m "test: define Case1 vibration feature interface"`

If Git is unavailable, leave the files in place and continue without destructive repository setup.

### Task 2: Add Isolation Forest detection and anomaly-type rules

**Files:**
- Modify: `case1_vibration_isolation_forest.py`
- Modify: `tests/test_case1_vibration_isolation_forest.py`

**Interfaces:**
- `detect_anomalies` returns the original columns plus `anomaly_score`, `is_anomaly`, and `anomaly_type`.
- `classify_anomalies` labels only rows where `is_anomaly` is true; normal rows receive `normal`.

- [ ] **Step 1: Write failing tests for spike detection and normal-row labeling**

```python
from case1_vibration_isolation_forest import detect_anomalies


def test_detect_anomalies_marks_a_large_spike():
    values = np.ones(80)
    values[60] = 8.0
    frame = pd.DataFrame({"Timestamps": pd.date_range("2026-01-01", periods=80, freq="s"), "Vibration": values})
    result = detect_anomalies(frame, contamination=0.05, n_estimators=100, random_state=42, short_window=5, long_window=15, slope_window=7)
    assert bool(result.loc[60, "is_anomaly"])
    assert result.loc[0, "anomaly_type"] == "normal"


def test_classification_can_identify_increased_variability():
    values = np.r_[np.ones(50), np.tile([0.5, 1.5], 15)]
    frame = pd.DataFrame({"Timestamps": pd.date_range("2026-01-01", periods=len(values), freq="s"), "Vibration": values})
    result = detect_anomalies(frame, contamination=0.10, n_estimators=100, random_state=42, short_window=5, long_window=15, slope_window=7)
    assert "std_increase" in set(result.loc[result["is_anomaly"], "anomaly_type"])
```

- [ ] **Step 2: Run tests and verify they fail for the missing detection behavior**

Run: `pytest -q tests/test_case1_vibration_isolation_forest.py -k "spike or variability"`

Expected: FAIL because `detect_anomalies` is not implemented yet.

- [ ] **Step 3: Implement detection and classification**

Fit `sklearn.ensemble.IsolationForest` on the seven feature columns. Set `anomaly_score = -decision_function(features)` so higher means more anomalous, and set `is_anomaly = (predict(features) == -1)`. Implement ordered rules for `gradual_increase`, `increase_1_to_5pct`, `std_increase`, and `repeated_spike`, with fallback `general_anomaly`.

- [ ] **Step 4: Run all unit tests and confirm they pass**

Run: `pytest -q tests/test_case1_vibration_isolation_forest.py`

Expected: PASS with zero failures.

### Task 3: Add workbook loading, CLI, CSV export, and real-data smoke test

**Files:**
- Modify: `case1_vibration_isolation_forest.py`
- Modify: `tests/test_case1_vibration_isolation_forest.py`
- Create: `requirements.txt`

**Interfaces:**
- `load_case1(input_path) -> pandas.DataFrame`
- `main(argv=None) -> int`

- [ ] **Step 1: Write failing tests for input validation and output shape**

```python
from pathlib import Path

from case1_vibration_isolation_forest import load_case1


def test_load_case1_requires_case1_vibration_columns(tmp_path):
    bad_path = tmp_path / "bad.xlsx"
    pd.DataFrame({"wrong": [1]}).to_excel(bad_path, index=False)
    with pytest.raises(ValueError, match="Case1.*Vibration"):
        load_case1(bad_path)


def test_real_workbook_case1_smoke():
    path = Path(__file__).parents[1] / "AI Model Raw Data.xlsx"
    result = detect_anomalies(load_case1(path), contamination=0.01, n_estimators=50, random_state=42, short_window=15, long_window=60, slope_window=30)
    assert len(result) == 93214
    assert result["is_anomaly"].dtype == bool
    assert result["anomaly_type"].notna().all()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/test_case1_vibration_isolation_forest.py -k "load_case1 or real_workbook"`

Expected: FAIL because loading and CLI integration are not implemented.

- [ ] **Step 3: Implement loader and CLI**

Read `sheet_name="Case1"`, require `Timestamps` and `Vibration`, sort by timestamp, drop duplicate timestamps, coerce values, and drop invalid rows. Add `argparse` options for input, output, contamination, estimators, random state, and window sizes. Save the final DataFrame with `to_csv(index=False, encoding="utf-8-sig")` and return `0`.

- [ ] **Step 4: Add dependencies**

Create `requirements.txt` with:

```text
pandas>=2.0
numpy>=1.24
scikit-learn>=1.2
openpyxl>=3.1
pytest>=7.0
```

- [ ] **Step 5: Run the complete test suite and real-data command**

Run: `pytest -q`

Expected: all tests pass.

Run: `python case1_vibration_isolation_forest.py --input "AI Model Raw Data.xlsx" --output "case1_vibration_anomaly_results.csv"`

Expected: exit code `0`, and the CSV contains 93,214 rows.

### Task 4: Final verification and usage documentation

**Files:**
- Modify: `case1_vibration_isolation_forest.py` only if verification exposes a defect
- Create: `README.md`

- [ ] **Step 1: Inspect the generated CSV**

Use Python to confirm the expected columns, row count, non-null anomaly labels, and anomaly count by type.

- [ ] **Step 2: Run syntax and test verification**

Run: `python -m py_compile case1_vibration_isolation_forest.py` and `pytest -q`.

- [ ] **Step 3: Document installation, execution, output columns, and tuning guidance**

Document that Isolation Forest is unsupervised, that `contamination` is an expected anomaly proportion, and that the four requested types are heuristic interpretations layered on top of the model result.

- [ ] **Step 4: Confirm final file paths and report evidence**

Check that the script, requirements, README, tests, and generated CSV exist, then report the exact command and verification counts.
