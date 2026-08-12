# Stitch 대시보드 FastAPI 연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stitch에서 추출한 다섯 개 HTML 화면을 FastAPI와 기존 Case1 Isolation Forest 분석 코드에 연결해 로컬에서 실행 가능한 진동 이상탐지 대시보드를 구축한다.

**Architecture:** FastAPI가 정적 HTML을 제공하고, 화면별 JavaScript는 JSON API에서 조회한 결과를 카드·표·차트에 반영한다. 분석 결과 CSV를 기본 조회 대상으로 사용하며, 설정 저장 후에는 기존 분석 함수를 다시 실행하여 원자적으로 결과를 갱신한다.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, pandas, Pydantic, 기존 scikit-learn Isolation Forest, HTML/Tailwind CDN, Chart.js CDN, pytest.

## Global Constraints

- 데이터 원본은 `AI Model Raw Data.xlsx`의 `Case1` 시트만 사용한다.
- 현장 고장을 확정했다고 표현하지 않으며, `raw_anomaly`는 후보·`confirmed_anomaly`는 확정 경보로 구분한다.
- 선택한 시간 범위가 경보 수·차트·목록에 일관되게 반영되어야 한다.
- 원본 Excel, 분석 산출물, 가상환경, 비밀값은 GitHub에 추가하지 않는다.
- 초기 버전은 로컬 PC 실행만 지원하며 실시간 설비 연동·로그인·외부 DB는 포함하지 않는다.

---

## File structure

```text
backend/
  __init__.py                 # backend package marker
  config.py                   # validated model settings and local JSON persistence
  data_service.py             # CSV loading, date filtering, dashboard response builders
  analysis_service.py         # rerun existing model and synthetic evaluation safely
  main.py                     # FastAPI app, static file serving, API routes
frontend/
  assets/app.js               # shared fetch, formatting, chart helpers
  overview.html               # copied/adapted Stitch overview screen
  analysis.html               # copied/adapted Stitch analysis screen
  alarms.html                 # copied/adapted Stitch alarm screen
  performance.html            # copied/adapted Stitch performance screen
  settings.html               # copied/adapted Stitch settings screen
runtime/
  model_settings.json         # ignored local setting values created on first run
tests/
  test_backend_config.py      # settings validation and persistence tests
  test_backend_data_service.py# time range, status, alert aggregation tests
  test_backend_api.py         # FastAPI endpoint tests against temporary CSV data
requirements.txt              # add FastAPI, Uvicorn, HTTP test dependency
README.md                     # dashboard installation and launch instructions
```

### Task 1: Add backend configuration and dependencies

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `tests/test_backend_config.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces `ModelSettings`, `load_settings(path)`, `save_settings(settings, path)`.
- `ModelSettings` has `threshold_quantile: float`, `persistence_seconds: int`, `n_estimators: int`, `random_state: int`, `short_window: int`, `long_window: int`, and `slope_window: int`.

- [ ] **Step 1: Write failing settings tests**

```python
from backend.config import ModelSettings, load_settings, save_settings

def test_settings_round_trip(tmp_path):
    path = tmp_path / "model_settings.json"
    settings = ModelSettings(threshold_quantile=0.998, persistence_seconds=6)
    save_settings(settings, path)
    assert load_settings(path) == settings

def test_settings_rejects_invalid_window_order():
    with pytest.raises(ValueError):
        ModelSettings(short_window=61, long_window=60)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_config.py -v`

Expected: import failure because `backend.config` does not exist.

- [ ] **Step 3: Implement validated JSON settings persistence**

```python
@dataclass(frozen=True)
class ModelSettings:
    threshold_quantile: float = 0.999
    persistence_seconds: int = 5
    n_estimators: int = 300
    random_state: int = 42
    short_window: int = 15
    long_window: int = 60
    slope_window: int = 30

    def __post_init__(self):
        if not 0.5 < self.threshold_quantile < 1.0:
            raise ValueError("threshold_quantile must be between 0.5 and 1.0")
        if self.persistence_seconds < 1 or self.n_estimators < 1:
            raise ValueError("persistence_seconds and n_estimators must be positive")
        if not 0 < self.short_window <= self.long_window or self.slope_window < 2:
            raise ValueError("window values are inconsistent")
```

Use `json.dumps(asdict(settings), ensure_ascii=False, indent=2)` and replace a temporary file with `Path.replace()` after a successful write. Add `fastapi>=0.115`, `uvicorn[standard]>=0.30`, and `httpx>=0.27` to requirements.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/__init__.py backend/config.py tests/test_backend_config.py requirements.txt
git commit -m "feat: add dashboard model settings"
```

### Task 2: Build result-data and analysis services

**Files:**
- Create: `backend/data_service.py`
- Create: `backend/analysis_service.py`
- Create: `tests/test_backend_data_service.py`

**Interfaces:**
- Consumes the output fields from `detect_anomalies`: `Timestamps`, `Vibration`, all feature columns, `anomaly_score`, `threshold`, `raw_anomaly`, `confirmed_anomaly`, `is_anomaly`, `anomaly_type`.
- Produces `load_results(path) -> pd.DataFrame`, `filter_results(frame, start, end) -> pd.DataFrame`, `overview_payload(frame) -> dict`, `alerts_payload(frame) -> dict`, and `rerun_analysis(settings, paths) -> pd.DataFrame`.

- [ ] **Step 1: Write failing range and status tests**

```python
def test_filter_and_overview_use_selected_time_range(sample_results):
    ranged = filter_results(sample_results, "2026-07-11T00:00:01", "2026-07-11T00:00:02")
    overview = overview_payload(ranged)
    assert overview["confirmed_alarm_count"] == 1
    assert overview["latest"]["status"] == "confirmed_anomaly"

def test_alert_breakdown_keeps_raw_and_confirmed_separate(sample_results):
    payload = alerts_payload(sample_results)
    assert payload["raw_candidate_count"] == 2
    assert payload["confirmed_alarm_count"] == 1
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_data_service.py -v`

Expected: import failure because `backend.data_service` does not exist.

- [ ] **Step 3: Implement CSV transforms and atomic reanalysis**

`load_results` parses `Timestamps` as datetimes and converts boolean result columns. `filter_results` applies inclusive date bounds. `overview_payload` calculates normal/abnormal means only from the filtered frame and labels the latest status as `normal`, `raw_candidate`, or `confirmed_anomaly`. `rerun_analysis` loads Case1 via `load_case1`, calls `detect_anomalies` using `ModelSettings`, writes a temporary UTF-8-SIG CSV, and replaces the previous result only after success. It invokes `evaluate_synthetic_test` with the same model-sensitive settings and writes the small metrics CSV atomically.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_data_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/data_service.py backend/analysis_service.py tests/test_backend_data_service.py
git commit -m "feat: add dashboard data services"
```

### Task 3: Expose tested FastAPI routes and static frontend

**Files:**
- Create: `backend/main.py`
- Create: `tests/test_backend_api.py`
- Create: `frontend/assets/app.js`

**Interfaces:**
- Consumes `ModelSettings`, `load_settings`, `save_settings`, `load_results`, `filter_results`, `overview_payload`, `alerts_payload`, `rerun_analysis`.
- Produces GET APIs for overview, trend, analysis, alarms, performance, settings; PUT settings; POST reanalysis; and serves `/` as `frontend/overview.html`.

- [ ] **Step 1: Write failing API tests**

```python
from fastapi.testclient import TestClient
from backend.main import create_app

def test_overview_and_alarm_counts_respect_range(tmp_path, sample_results):
    app = create_app(results_path=write_csv(tmp_path, sample_results), settings_path=tmp_path / "settings.json")
    client = TestClient(app)
    response = client.get("/api/overview", params={"start": "2026-07-11T00:00:01", "end": "2026-07-11T00:00:02"})
    assert response.status_code == 200
    assert response.json()["confirmed_alarm_count"] == 1
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_api.py -v`

Expected: import failure because `backend.main` does not exist.

- [ ] **Step 3: Implement the API application**

Create `create_app(...)` for tests and module-level `app = create_app()` for Uvicorn. Use `StaticFiles` and explicit `FileResponse` routes for the five HTML pages. Return HTTP 404 for missing output files, HTTP 422 for invalid settings, and HTTP 500 with a concise safe message if reanalysis fails. In `app.js`, provide `requestJson(path, params)`, `formatNumber(value)`, `formatDate(value)`, `statusLabel(status)`, and Chart.js creation helpers without embedding data values in HTML.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/main.py frontend/assets/app.js tests/test_backend_api.py
git commit -m "feat: expose vibration dashboard API"
```

### Task 4: Adapt the five Stitch screens to live API data

**Files:**
- Create: `frontend/overview.html` from `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_4/code.html`
- Create: `frontend/analysis.html` from `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_1/code.html`
- Create: `frontend/alarms.html` from `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_2/code.html`
- Create: `frontend/performance.html` from `stitch_vibration_insight_analysis_dashboard/code.html`
- Create: `frontend/settings.html` from `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_3/code.html`
- Modify: `frontend/assets/app.js`

**Interfaces:**
- Consumes the routes from Task 3.
- Produces HTML pages whose values are populated with `data-*` targets and whose sidebar links point to the other four pages.

- [ ] **Step 1: Add page-level DOM targets before wiring data**

Add stable IDs rather than relying on matched visible text, for example:

```html
<span id="current-vibration">-</span>
<span id="current-short-mean">-</span>
<span id="anomaly-score">-</span>
<span id="score-threshold">-</span>
<span id="confirmed-alarm-count">-</span>
<canvas id="overview-trend-chart"></canvas>
```

Use `overview.html` for summary cards and selected-range trend; `analysis.html` for feature chart selectors; `alarms.html` for filterable candidate/confirmed rows; `performance.html` for synthetic-only metrics and a visible qualification note; `settings.html` for a validated form and two actions: save, save-and-rerun.

- [ ] **Step 2: Implement page initializers in the shared script**

```javascript
async function initializeOverview() {
  const range = getSelectedRange();
  const [overview, trend] = await Promise.all([
    requestJson('/api/overview', range),
    requestJson('/api/trend', range),
  ]);
  renderOverview(overview);
  renderTrend(trend);
}
```

Create equivalent `initializeAnalysis`, `initializeAlarms`, `initializePerformance`, and `initializeSettings` functions. Change a time-range input by re-fetching all values used on that page. Draw red confirmed markers, amber raw-only markers, and blue/green normal states. Label all anomaly semantics in Korean.

- [ ] **Step 3: Run the server and inspect every page manually**

Run: `.venv\Scripts\python.exe -m uvicorn backend.main:app --reload`

Verify: `/`, `/analysis`, `/alarms`, `/performance`, `/settings` load with no JavaScript console errors; one range change changes alarm count and table; saving valid settings succeeds; reanalysis refreshes overview data.

- [ ] **Step 4: Commit**

```powershell
git add frontend
git commit -m "feat: connect Stitch dashboard screens"
```

### Task 5: Complete documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `.gitignore`

**Interfaces:**
- Documents the server entry point `backend.main:app` and the expected local Excel filename.

- [ ] **Step 1: Add dashboard launch instructions**

Document these exact PowerShell commands:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

State the browser URLs: `http://127.0.0.1:8000/`, `/analysis`, `/alarms`, `/performance`, `/settings`. Explain that local `runtime/`, result CSVs, and source Excel are intentionally ignored by Git.

- [ ] **Step 2: Run all automated tests**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all original model tests and new backend/API tests pass.

- [ ] **Step 3: Verify ignored files and staged scope**

Run:

```powershell
git check-ignore -v "AI Model Raw Data.xlsx" ".venv" "case1_vibration_anomaly_results.csv"
git status -sb
```

Expected: raw input, virtual environment, and generated results are ignored; only source, tests, docs, and frontend changes are staged for publication.

- [ ] **Step 4: Commit**

```powershell
git add README.md .gitignore
git commit -m "docs: add dashboard launch guide"
```
