# Case1 Vibration Isolation Forest 설계

## 목표

`AI Model Raw Data.xlsx`의 `Case1` 시트에서 `Vibration` 열만 사용해 진동 이상변화를 탐지한다. 현재 `구분` 열은 모든 행이 `정상`이므로, 라벨을 학습에 사용하지 않는 비지도 탐지로 구성한다.

## 입력과 출력

- 입력: `Case1` 시트의 `Timestamps`, `Vibration`
- 출력: 원본 시각, 진동값, 생성 특징, Isolation Forest 점수, 이상 여부, 이상 유형을 포함한 CSV
- 기본 출력 파일: `case1_vibration_anomaly_results.csv`

## 탐지 설계

1. 타임스탬프를 날짜시간으로 변환하고 진동값을 숫자로 변환한다.
2. 결측값은 제거하고 타임스탬프 중복은 첫 행을 유지한다.
3. 시계열 특징을 만든다.
   - 단기 이동평균 및 이동표준편차
   - 장기 이동평균 및 이동표준편차
   - 1차 차분 절대값
   - 단기-장기 평균 차이
   - 단기 구간 선형회귀 기울기
4. 특징이 준비된 행을 Isolation Forest에 입력한다.
5. `contamination`은 기본 `0.01`, `n_estimators`는 기본 `300`, `random_state`는 고정값으로 둔다.
6. `decision_function`이 낮은 행을 이상으로 판정하고, 사용자가 조정할 수 있도록 CLI 옵션을 제공한다.

## 이상 유형 분류

Isolation Forest의 이상 판정과 유형 분류는 분리한다. 분류 규칙은 설명 가능성을 위해 결과 CSV에 함께 기록한다.

- `gradual_increase`: 단기-장기 평균 차이와 단기 추세 기울기가 지속적으로 양수
- `increase_1_to_5pct`: 장기 기준 대비 현재 단기 평균이 1~5% 높음
- `std_increase`: 단기 이동표준편차가 장기 이동표준편차보다 높음
- `repeated_spike`: 차분 절대값과 국소 피크가 반복적으로 높음
- 위 규칙에 해당하지 않으면 `general_anomaly`

유형 분류는 반드시 Isolation Forest 이상 행에만 적용하며, 이상이 아닌 행은 `normal`로 기록한다.

## 실행 방식

`python case1_vibration_isolation_forest.py --input "AI Model Raw Data.xlsx" --output case1_vibration_anomaly_results.csv` 형태로 실행한다. 윈도우 크기, 오염도, 트리 수를 옵션으로 변경할 수 있게 한다.

## 검증 기준

- Case1을 정상적으로 읽고 결과 행 수가 유효한 입력 행 수와 일치한다.
- 결과에 이상 점수와 이상 여부가 존재한다.
- 입력 파일이 없거나 `Case1`/`Vibration` 열이 없을 때 명확한 오류를 낸다.
- 합성 데이터 테스트에서 급격한 스파이크와 지속 증가 구간이 이상으로 표시된다.
