# Stitch 레이아웃 재연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 새 Google Stitch HTML 다섯 화면의 레이아웃을 유지하면서 Case1 Isolation Forest의 실제 데이터와 FastAPI를 다시 연결한다.

**Architecture:** `frontend/`의 현재 간단 페이지를 새 Stitch 추출 HTML로 교체하고, 공통 JavaScript가 FastAPI JSON을 화면별 DOM 대상에 렌더링한다. FastAPI는 기존 분석 결과 CSV 조회를 유지하며, 재분석 때 합성 성능 지표 CSV도 원자적으로 함께 갱신해 성능 평가 화면에 제공한다.

**Tech Stack:** Python 3.12, FastAPI, pandas, scikit-learn Isolation Forest, HTML/Tailwind CDN, Chart.js CDN, pytest.

## Global Constraints

- 데이터 원본은 `AI Model Raw Data.xlsx`의 `Case1` 시트만 사용한다.
- `raw_anomaly`는 **이상 후보**, `confirmed_anomaly`와 `is_anomaly`는 **확정 경보**로 표시하며 실제 설비 고장으로 표현하지 않는다.
- Stitch HTML의 Tailwind 스타일, 화면 배치, 사이드바와 시각적 구성은 유지한다.
- 선택 시간 범위는 개요·진동 분석·알람 내역의 차트, 집계, 목록에 일관되게 적용한다.
- 모델 설정에서 동작하는 값은 `threshold_quantile`, `persistence_seconds`, `n_estimators`, `random_state`, `short_window`, `long_window`, `slope_window`뿐이다.
- 유형별 가중치와 개별 최소 지속시간은 현재 모델에서 지원하지 않으므로 비활성화하고 지원하지 않음을 표시한다.
- 실시간 설비·PLC 수집, 외부 DB, 로그인 및 권한 제어는 이번 변경에 포함하지 않는다.

---

## File structure

```text
backend/
  analysis_service.py     # 재분석과 합성 평가 결과 생성
  data_service.py         # 결과/성능 지표 CSV를 대시보드 JSON으로 변환
  main.py                 # 성능 API를 포함한 FastAPI routes
frontend/
  overview.html           # 새 Stitch 개요 화면에 실제 값 대상 추가
  analysis.html           # 새 Stitch 진동 분석 화면에 실제 차트/표 대상 추가
  alarms.html             # 새 Stitch 알람 내역 화면에 실제 목록/상세 대상 추가
  performance.html        # 새 Stitch 성능 평가 화면에 실제 성능 대상 추가
  settings.html           # 새 Stitch 모델 설정 화면에 실제 입력/버튼 대상 추가
  assets/app.js           # API 호출 및 화면별 렌더링
tests/
  test_backend_data_service.py  # 성능/분석 JSON 변환 테스트
  test_backend_api.py           # 성능 API, 선택 범위, 재분석 API 테스트
```

### Task 1: Add synthetic-performance storage and JSON payloads

**Files:**
- Modify: `backend/analysis_service.py`
- Modify: `backend/data_service.py`
- Create: `tests/test_backend_data_service.py`

**Interfaces:**
- `rerun_analysis(settings, input_path, output_path, metrics_path) -> pd.DataFrame` writes the analysis output and `synthetic_anomaly_metrics.csv` only after each corresponding calculation succeeds.
- `performance_payload(metrics_path) -> dict` returns `normal_false_positive_rate`, `overall_recall`, and `patterns` items with `anomaly_type`, `rows`, `detected_rows`, and `recall`.

- [ ] **Step 1: Write failing payload tests**

```python
def test_performance_payload_calculates_overall_recall(tmp_path):
    metrics = pd.DataFrame([
        {"anomaly_type": "normal", "recall": 0.0, "false_positive_rate": 0.003, "rows": 100},
        {"anomaly_type": "repeated_spike", "recall": 1.0, "false_positive_rate": 0.0, "rows": 30},
        {"anomaly_type": "std_increase", "recall": 0.5, "false_positive_rate": 0.0, "rows": 30},
    ])
    path = tmp_path / "metrics.csv"; metrics.to_csv(path, index=False)
    payload = performance_payload(path)
    assert payload["normal_false_positive_rate"] == 0.003
    assert payload["overall_recall"] == 0.75
    assert payload["patterns"][0]["detected_rows"] == 30
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_data_service.py -v`

Expected: FAIL because `performance_payload` does not exist.

- [ ] **Step 3: Implement metrics persistence and payload construction**

Call `evaluate_synthetic_test` after `detect_anomalies`, passing the same threshold quantile, persistence seconds, number of trees, and random seed. Write its metrics DataFrame to the configured metrics path via a `.tmp` file then replace. `performance_payload` must exclude the `normal` row from `patterns`, calculate `detected_rows` as `round(rows * recall)`, calculate overall recall as detected synthetic rows divided by all synthetic rows, and return the normal row's `false_positive_rate`.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_data_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/analysis_service.py backend/data_service.py tests/test_backend_data_service.py
git commit -m "feat: expose synthetic performance metrics"
```

### Task 2: Extend FastAPI with performance data and testable paths

**Files:**
- Modify: `backend/main.py`
- Create: `tests/test_backend_api.py`

**Interfaces:**
- `create_app(results_path, settings_path, metrics_path, input_path)` accepts test paths while preserving the current defaults.
- `GET /api/performance` returns `performance_payload(metrics_path)`.
- `POST /api/reanalyze` regenerates both result and metrics files, then returns total rows, confirmed alarm count, and performance summary.

- [ ] **Step 1: Write failing route tests**

```python
def test_performance_endpoint_returns_metrics(tmp_path, sample_results, sample_metrics):
    app = create_app(
        results_path=write_results(tmp_path, sample_results),
        settings_path=tmp_path / "settings.json",
        metrics_path=write_metrics(tmp_path, sample_metrics),
        input_path=tmp_path / "input.xlsx",
    )
    response = TestClient(app).get("/api/performance")
    assert response.status_code == 200
    assert response.json()["patterns"][0]["anomaly_type"] == "repeated_spike"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_api.py -v`

Expected: FAIL because the app has no `/api/performance` route or no compatible `create_app` signature.

- [ ] **Step 3: Implement the performance route and explicit runtime paths**

Add `METRICS = ROOT / "synthetic_anomaly_outputs" / "synthetic_anomaly_metrics.csv"`. Return 404 with Korean guidance to run reanalysis when metrics are absent. Pass the configured input and metrics paths to `rerun_analysis`. Keep existing overview/trend/analysis/alarms responses unchanged.

- [ ] **Step 4: Run focused API tests and existing tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backend_api.py tests/test_backend_data_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/main.py tests/test_backend_api.py
git commit -m "feat: add performance dashboard API"
```

### Task 3: Replace frontend pages with the new Stitch layout

**Files:**
- Modify: `frontend/overview.html` using `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_4/code.html`
- Modify: `frontend/analysis.html` using `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_2/code.html`
- Modify: `frontend/alarms.html` using `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_1/code.html`
- Modify: `frontend/performance.html` using `stitch_vibration_insight_analysis_dashboard/code.html`
- Modify: `frontend/settings.html` using `stitch_vibration_insight_analysis_dashboard/vibration_detection_model_3/code.html`

**Interfaces:**
- Each HTML body has `data-page` matching `overview`, `analysis`, `alarms`, `performance`, or `settings`.
- Each page loads `/assets/app.js`, and chart pages load Chart.js before the shared script.
- Each data location used by `app.js` has a stable `id` or `data-*` attribute.

- [ ] **Step 1: Copy each matching Stitch HTML as the page base**

Keep the original Tailwind configuration, fonts, dark theme classes, sidebar structure, and content grouping. Change sidebar anchors to `/`, `/analysis`, `/alarms`, `/performance`, and `/settings`. Add `defer` script loading:

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script defer src="/assets/app.js"></script>
```

- [ ] **Step 2: Add stable targets for live values**

Use these IDs in the new layout:

```html
<!-- overview -->
<span id="overview-current-vibration">-</span>
<span id="overview-short-mean">-</span>
<span id="overview-score">-</span>
<span id="overview-threshold">-</span>
<span id="overview-alarm-count">-</span>
<span id="overview-status">-</span>
<canvas id="overview-trend-chart"></canvas>

<!-- alarms -->
<tbody id="alarm-rows"></tbody>
<section id="alarm-detail"></section>

<!-- performance -->
<span id="performance-fpr">-</span>
<span id="performance-recall">-</span>
<tbody id="performance-pattern-rows"></tbody>
```

Add per-page time inputs with IDs `range-start`, `range-end` and a button `range-apply` on overview, analysis, and alarms. In settings, use exact input names from `ModelSettings` and mark unsupported controls `disabled aria-disabled="true"` with the Korean text `현재 모델에서 지원하지 않음`.

- [ ] **Step 3: Confirm page structure is valid**

Run: `rg -n 'data-page|/assets/app.js|overview-current-vibration|alarm-rows|performance-pattern-rows|현재 모델에서 지원하지 않음' frontend`

Expected: the required page marker, script, target IDs, and disabled-setting notice are present.

- [ ] **Step 4: Commit**

```powershell
git add frontend/overview.html frontend/analysis.html frontend/alarms.html frontend/performance.html frontend/settings.html
git commit -m "feat: apply updated Stitch dashboard layout"
```

### Task 4: Render live API data into the Stitch layouts

**Files:**
- Modify: `frontend/assets/app.js`

**Interfaces:**
- Consumes `/api/overview`, `/api/trend`, `/api/analysis`, `/api/alarms`, `/api/performance`, `/api/settings`, and `/api/reanalyze`.
- Provides `initializeOverview`, `initializeAnalysis`, `initializeAlarms`, `initializePerformance`, and `initializeSettings` selected by `document.body.dataset.page`.

- [ ] **Step 1: Replace the current static performance string with API rendering**

```javascript
async function initializePerformance() {
  const data = await requestJson('/api/performance');
  setText('performance-fpr', percent(data.normal_false_positive_rate));
  setText('performance-recall', percent(data.overall_recall));
  document.querySelector('#performance-pattern-rows').innerHTML = data.patterns.map(pattern => `
    <tr><td>${typeLabel(pattern.anomaly_type)}</td><td>${pattern.rows}</td>
    <td>${pattern.detected_rows}</td><td>${percent(pattern.recall)}</td></tr>`).join('');
}
```

- [ ] **Step 2: Implement overview, analysis, and alarms renderers**

Use API date parameters from `range-start` and `range-end`. The overview chart must render vibration and short mean lines with raw-only points in amber and confirmed points in red. The analysis chart must render vibration, short mean, anomaly score, and threshold; populate its result table with live rows. The alarm table must render candidate and confirmed rows and replace the detail panel when a row is selected.

- [ ] **Step 3: Implement settings form behavior**

Read only supported input names. `저장` sends `PUT /api/settings`; `저장 후 재분석` sends `POST /api/reanalyze`. Disable action buttons while a request is pending. After reanalysis, show row count, confirmed-alarm count, FPR, and overall recall returned by the API. Never collect or send disabled unsupported controls.

- [ ] **Step 4: Handle API errors in the visible layout**

Wrap each initializer in a common `runPage` function that sets a page-local `data-api-error` target to the Korean `detail` message returned by the server. Do not leave the page silently showing placeholder values on an API failure.

- [ ] **Step 5: Verify with the running server**

Run: `.venv\Scripts\python.exe -m uvicorn backend.main:app --reload`

Verify in the browser: all five routes load; range change updates overview alarm count and alarm rows; model settings show only supported inputs as active; save-and-reanalyze updates the performance page on refresh.

- [ ] **Step 6: Commit**

```powershell
git add frontend/assets/app.js
git commit -m "feat: render live data in Stitch layouts"
```

### Task 5: Final verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `.gitignore`

**Interfaces:**
- Documents that `stitch_vibration_insight_analysis_dashboard/` is a local design source, while `frontend/` is the served UI.

- [ ] **Step 1: Add design-update guidance**

Document that a new Stitch export should replace the matching source HTML and must preserve `data-page`, `/assets/app.js`, live-data IDs, and working sidebar links. State that `runtime/`, result CSVs, synthetic result files, and local Stitch ZIP exports remain ignored.

- [ ] **Step 2: Run automated verification**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all existing model tests and new backend/API tests pass.

- [ ] **Step 3: Run live HTTP verification**

Run the server and request each route and API:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/ | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8000/analysis | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8000/alarms | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8000/performance | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8000/settings | Select-Object StatusCode
```

Expected: all responses return `200`.

- [ ] **Step 4: Commit**

```powershell
git add README.md .gitignore
git commit -m "docs: explain Stitch layout update workflow"
```
