# Case1 진동 이상변화 탐지

`AI Model Raw Data.xlsx`의 `Case1` 시트에서 `Vibration` 데이터를 사용해 윈도우 특징 기반 Isolation Forest와 유형별 패턴 규칙을 결합한 이상탐지를 수행합니다.

## 설치

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 로컬 웹 대시보드

Stitch 기반 화면과 Case1 분석 결과를 웹으로 확인하려면 아래 명령을 실행합니다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000/`을 엽니다. 메뉴에서 진동 분석(`/analysis`), 알람 내역(`/alarms`), 성능 평가(`/performance`), 모델 설정(`/settings`)을 확인할 수 있습니다.

처음 실행했거나 분석 결과가 없으면 **모델 설정** 페이지에서 `저장 후 재분석`을 누르세요. `AI Model Raw Data.xlsx`의 `Case1` 데이터를 다시 분석한 뒤 웹 화면에 반영합니다. 분석 결과 CSV와 로컬 모델 설정은 실행 산출물이므로 GitHub에 저장하지 않습니다.

## 실행

```powershell
.venv\Scripts\python.exe case1_vibration_isolation_forest.py `
  --input "AI Model Raw Data.xlsx" `
  --output "case1_vibration_anomaly_results.csv"
```

기본값은 정상 기준 점수의 상위 0.1%를 임계값으로 사용하는 `threshold_quantile=0.999`, `persistence_seconds=5`, `n_estimators=300`, `random_state=42`입니다. 계산량과 민감도는 `--threshold-quantile`, `--persistence-seconds`, `--n-estimators`, `--short-window`, `--long-window`, `--slope-window` 옵션으로 조정할 수 있습니다.

## 결과 컬럼

- `Timestamps`, `Vibration`: 원본 Case1 데이터
- `short_mean`, `short_std`: 단기 이동평균·이동표준편차
- `long_mean`, `long_std`: 장기 이동평균·이동표준편차
- `diff_abs`: 인접 시점 간 진동 변화량
- `mean_gap`: 단기 평균과 장기 평균의 차이
- `slope`: 단기 추세 기울기
- `short_pct_change`: 장기 기준 대비 단기 평균의 상대 변화율
- `volatility_ratio`: 단기 표준편차/장기 표준편차
- `spike_count`: 최근 윈도우 내 기준 초과 스파이크 개수
- `anomaly_score`: Isolation Forest 이상 점수. 값이 클수록 이상 가능성이 높음
- `threshold`: 정상 기준 점수 분포에서 학습한 이상 임계값
- `raw_anomaly`: 임계값을 한 번이라도 초과했는지 여부
- `confirmed_anomaly`: 임계값 초과가 최소 `persistence_seconds`초 연속인지 여부
- `is_anomaly`: 최종 경보 여부. 기본적으로 `confirmed_anomaly`와 동일
- `anomaly_type`: `normal`, `gradual_increase`, `increase_1_to_5pct`, `std_increase`, `repeated_spike`, `general_anomaly`

`anomaly_type`은 최종 경보 행에 대해 특징값을 바탕으로 분류하는 설명용 휴리스틱입니다. `threshold_quantile`을 높이면 더 드문 변화만 후보가 되고, `persistence_seconds`를 높이면 더 오래 지속되는 변화만 최종 경보가 됩니다. 현재 파일처럼 정상 데이터만 있을 때는 임계값이 정상 기준 분포에서 계산됩니다.

## 합성 이상 검증

원본 정상 데이터로만 모델을 학습한 뒤, 별도 테스트 복사본에 합성 이상을 삽입해 탐지율과 정상 구간 오탐지율을 계산할 수 있습니다.

```powershell
.venv\Scripts\python.exe synthetic_anomaly_evaluation.py `
  --input "AI Model Raw Data.xlsx" `
  --output-dir "synthetic_anomaly_outputs"
```

이 검증은 실제 고장 라벨을 대체하지 않으며, 이상 유형별 민감도와 임계값 조정 방향을 확인하기 위한 테스트입니다.
