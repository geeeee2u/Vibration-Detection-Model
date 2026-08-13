# Stitch 레이아웃 재연결 설계

## 목적

`stitch_vibration_insight_analysis_dashboard`에 새로 저장된 Google Stitch HTML 다섯 화면을 대시보드의 새 화면 기반으로 사용한다. 기존 FastAPI와 Case1 Isolation Forest 분석 흐름은 유지하며, Stitch에 포함된 고정 예시 값·그래프·표를 실제 분석 데이터로 교체한다.

## 화면 원본과 경로

| Stitch 파일 | 웹 경로 | 역할 |
|---|---|---|
| `vibration_detection_model_4/code.html` | `/` | 개요 |
| `vibration_detection_model_2/code.html` | `/analysis` | 진동 분석 |
| `vibration_detection_model_1/code.html` | `/alarms` | 알람 내역 |
| `code.html` | `/performance` | 성능 평가 |
| `vibration_detection_model_3/code.html` | `/settings` | 모델 설정 |

## 연결 원칙

- Stitch HTML의 Tailwind 스타일, 화면 배치, 사이드바 및 시각적 구성은 유지한다.
- 정적 숫자, 정적 SVG 차트, 예시 경보 행은 API 응답으로 렌더링되는 DOM 영역으로 교체한다.
- 모든 페이지에 공통 데이터 요청·형식화·오류 표시 코드를 제공하되, 화면별 렌더링은 별도 초기화 함수로 구분한다.
- 사이드바 링크는 FastAPI가 제공하는 실제 웹 경로를 사용한다.
- `raw_anomaly`는 **이상 후보**, `confirmed_anomaly` 및 `is_anomaly`는 **확정 경보**로 계속 구분한다. 확정 경보를 실제 설비 고장으로 표현하지 않는다.

## 화면별 실제 데이터

### 개요

`/api/overview`와 `/api/trend`를 사용한다. 최신 `Vibration`, `short_mean`, `anomaly_score`, `threshold`, 점수 차이, 선택 시간 범위의 확정 경보 수, 현재 상태를 표시한다. 추세 영역은 진동값과 단기 이동평균을 Chart.js로 그리며, 후보는 황색·확정 경보는 적색으로 표시한다.

### 진동 분석

`/api/analysis`을 사용한다. 진동 추세, 이동평균, Isolation Forest 이상 점수와 임계값, 주요 특징량을 기간 선택에 따라 갱신한다. 분석 결과 표에는 시각, 후보/확정 상태, 주요 기여 특성, 점수, 조치 안내를 표시한다.

### 알람 내역

`/api/alarms`을 사용한다. 경보 목록은 발생 시각, 진동값, 단기 평균, 이상 점수, 임계값, 상태, 이상 유형을 실제 값으로 표시한다. 행을 선택하면 상세 패널도 같은 행 데이터로 갱신한다.

### 성능 평가

합성 이상 평가 지표를 API로 제공한다. 성능 화면은 정상 구간 오탐지율, 전체 합성 이상 탐지율, 유형별 삽입 행 수·탐지 행 수·탐지율을 표시한다. 합성 검증은 실제 현장 고장 성능을 보장하지 않는다는 안내를 유지한다.

### 모델 설정

현재 모델 코드가 지원하는 `threshold_quantile`, `persistence_seconds`, `n_estimators`, `random_state`, `short_window`, `long_window`, `slope_window`만 저장 및 재분석 동작에 연결한다. Stitch 화면의 유형별 가중치·개별 지속시간은 현재 분석 코드에 해당 기능이 없으므로 비활성화하고 “현재 모델에서는 지원하지 않음”으로 표시한다. 저장은 설정 JSON을 갱신하고, 저장 후 재분석은 원본 Excel을 다시 분석한 뒤 결과와 합성 평가 지표를 갱신한다.

## 백엔드 보완

현재 분석 결과 API를 유지하고, 성능 평가 API와 합성 평가 결과 생성·저장을 추가한다. 분석 결과 파일이나 합성 지표 파일이 없는 첫 실행에서는 설정 화면의 재분석을 안내하는 오류를 반환한다. 시간 범위는 개요·진동 분석·알람 내역의 모든 집계와 목록에 동일하게 적용한다.

## 검증

- 다섯 웹 경로가 새 Stitch 레이아웃으로 열리고 API 호출 실패 시 사용자에게 오류를 표시한다.
- 재분석 후 개요, 분석, 알람, 성능 평가 값이 같은 결과 기준으로 갱신된다.
- 설정 저장 시 지원하는 값만 저장되며, 지원하지 않는 유형별 조정값은 분석 결과에 영향을 주지 않는다.
- 원래 모델 테스트와 새 API 테스트를 모두 실행한다.

## 제외 범위

- 실시간 설비·PLC 수집, 외부 DB, 로그인 및 권한 제어
- 유형별 가중치와 유형별 최소 지속시간의 실제 모델 로직 구현
- 실제 고장 라벨에 근거한 현장 성능 확정
