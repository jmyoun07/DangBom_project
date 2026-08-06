# DB-care — 당뇨 합병증 예측 프로그램

병원 내부용 데스크톱 앱. 환자 검사수치를 입력하면 6개 ML 모델이 합병증 위험도를 예측하고,
슬라이더 시뮬레이션으로 치료 방치 / 집중관리 시나리오를 비교하며, 비슷한 졸업자 사례를 보여준다.

FastAPI(Python) + React(Vite) 를 Tauri 데스크톱 셸로 감싼 단일 실행 파일 구조다.
서버·인터넷 연결 없이 병원 PC 안에서만 동작하며, 데이터는 로컬 SQLite 에 저장된다.

**이 문서 하나로 설치·운영·개발·빌드가 모두 가능하다.**

- 프로그램만 쓴다면 → [1. 설치와 사용](#1-설치와-사용)
- 코드를 수정한다면 → [3. 개발 환경](#3-개발-환경) 부터

---

## 1. 설치와 사용

### 설치

1. `DB-care_x.y.z_x64-setup.exe` 실행 → 설치 마법사 진행 → 바탕화면 아이콘으로 실행
2. 별도 서버 설정이나 인터넷 연결이 필요 없다

### 환자 데이터 넣기

- **여러 명** — 홈 화면에서 CSV/엑셀 드래그&드롭. 화면의 "예시 템플릿 다운로드" 로 받은
  양식에 맞춰 채운다.
- **한 명** — 홈 화면 "직접 입력".

넣어야 할 값은 **병원이 실제로 측정하는 항목뿐**이다. 나이·BMI·eGFR·LDL·당뇨 이환기간 등은
프로그램이 자동으로 계산한다([4장](#자동-계산되는-값) 참고).

### 졸업자 데이터 넣기 (유사사례 기능)

유사사례 페이지는 **졸업자 데이터**를 근거로 동작한다. 최초 1회 업로드가 필요하다.

- 프로그램 → **설정** → **졸업자 엑셀 업로드**
- "졸업자 N명" 이 표시되면 완료

> 이 데이터 파일과 앞으로 채워 나갈 입력 양식은 **환자 실명·차트번호가 들어 있어
> 소스코드와 분리해 별도 전달**한다. 업로드 전까지 유사사례 페이지만 비어 있고
> 나머지 기능은 정상 동작한다.

**갱신 방법** — 전달받은 양식에 채워 같은 자리에서 다시 업로드한다.

- 1명 = 2줄 (초진 1줄 + 졸업 1줄), `visit_type` 으로 구분
- 같은 사람의 두 줄은 **`chart_no` 가 완전히 같아야** 한 사람으로 묶인다
- 검사를 안 한 항목은 `0` 이 아니라 **빈칸**으로 둔다 (`0` 은 측정값 0 으로 처리된다)
- 숫자 칸에는 숫자만 — `7.2%`, `120 mmHg` 같은 표기는 피한다
- **업로드하면 기존 명단을 전부 교체한다.** 추가된 사람만 담지 말고, 항상 전체 명단이 든
  하나의 파일로 관리한다
- 합병증 위험도는 입력하지 않는다. 검사 수치를 넣으면 ML 이 계산한다

### 데이터 위치와 백업

| | 경로 |
|---|---|
| Windows | `%APPDATA%\DB-care\dbcare.db` |
| macOS | `~/Library/Application Support/DB-care/dbcare.db` |

프로그램을 다시 설치해도 유지된다. 백업은 **설정 → 전체 환자 데이터 백업(CSV)**.
오류가 나면 같은 폴더의 `backend.log` 를 확인한다.

---

## 2. 화면 구성

| 경로 | 화면 | 내용 |
|---|---|---|
| `/home` | 데이터 업로드 | CSV·엑셀 업로드, 매핑 미리보기, 유효성 검사 |
| `/patients` | 환자 목록 | 이름·차트번호·연락처 통합 검색, 위험도 필터 |
| `/patients/:id` | 환자 상세 | 기본정보, AI 예측 결과, 수치 추이, 검사 수치표 |
| `/dashboard/:id` | 대시보드 | 6개 합병증 카드, 위험 요인 분석 |
| `/risk-analysis/:id` | 시나리오 분석 | C-peptide·HbA1c 슬라이더 → 방치/집중관리 비교 |
| `/case-comparison/:id` | 유사 사례 | 비슷한 졸업자 3명의 개선 사례 |
| `/settings` | 설정 | 졸업자 업로드, 백업, 데이터 관리 |

색상 규칙 — 고위험 `#ef4444` / 중위험 `#f59e0b` / 저위험 `#22c55e` / 강조 `#6366f1`.

---

## 3. 개발 환경

### 요구 버전

| 도구 | 버전 | 비고 |
|---|---|---|
| **Python** | **3.11** | ⚠️ 3.9 / 3.10 은 `shap` 설치 실패. 3.12+ 는 미검증 |
| **Node.js** | **20.19 이상** | Vite 요구 사항 |
| Rust | stable (MSVC) | Windows 설치 파일 빌드 시에만 |

### 실행

```bash
# 백엔드 (터미널 1)
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python -m uvicorn main:app --port 8000 --reload

# 프론트엔드 (터미널 2)
cd frontend
npm ci
npm run dev            # http://localhost:5173
```

환경변수 — `DBCARE_DB_PATH` 로 DB 파일 위치 변경, `DBCARE_SEED=1` 로 시연용 환자 10명 생성.

### 테스트

```bash
cd backend
for t in tests/*.py; do PYTHONPATH=. .venv/bin/python "$t"; done
```

배포 전에는 전부 통과해야 한다. 외부 데이터 파일 없이 단독으로 돌아간다.

| 테스트 | 지키는 것 |
|---|---|
| `test_graduate_upload_robustness` | 병원이 수기로 채운 엑셀의 14가지 변형(날짜 형식·단위 표기·컬럼 삭제 등) |
| `test_clinical_ranges_sync` | 업로드 경로와 API 경로의 허용 범위가 어긋나지 않을 것 |
| `test_legacy_value_resilience` | 구버전이 저장한 이상값 때문에 조회가 500 나지 않을 것 |
| `test_contributions` | 환자별 위험 변수(SHAP)가 실측 항목에서만 나올 것 |
| `test_clinical_floor_rule_scope` · `test_scenario_rule_scope` | 임상 안전망 규칙의 적용 범위 |
| `test_patient_crud_paths` · `test_visit_master_fields_sync` | 등록·수정·조회 경로와 방문 이력 컬럼 정합 |

---

## 4. 예측 로직

### 모델

6개 질환 모두 학습된 모델(`.pkl`)이 포함돼 있어 그대로 예측에 쓸 수 있다.

| 질환 | 파일 | 알고리즘 |
|---|---|---|
| 망막병증 | `retinopathy_model.pkl` | XGBoost (42 변수) |
| 신장질환 | `dkd_model.pkl` | Stacking (XGB+LGB+CatBoost → LogisticRegression) |
| 심혈관 | `cvd_model.pkl` | EasyEnsemble |
| 신경병증 | `neuropathy_final.pkl` | — |
| 치매 | `dementia_final.pkl` | — |
| 뇌혈관 | `cerebrovascular_final.pkl` | — |

`.pkl` 이 없거나 로드에 실패해도 앱은 죽지 않고 더미 값으로 넘어간다.
학습 원본 데이터(국민건강영양조사)는 재배포 제한이 있어 포함하지 않았다.
재학습이 필요하면 원자료를 직접 확보해야 한다.

### 입력 변수 (공통 38개)

```
인구통계(2)   age, sex
당뇨(4)       DM_duration, DM_diagnosis_age, DM_medication, insulin_medication
혈당(2)       HE_glu, HE_HbA1c
저항성(1)     TyG_index
지질(5)       HE_chol, HE_HDL_st2, HE_TG, LDL_calc, non_HDL
신장(2)       HE_crea, eGFR
혈압(4)       SBP, DBP, pulse_pressure, hypertension
계측(3)       HE_BMI, HE_ht, HE_wt
간효소(2)     HE_ast, HE_alt
소변(9)       단백·당·잠혈·빌리루빈·케톤·유로빌리노겐·아질산염·pH·비중
생활습관(4)   smoking, drinking, exercise, sleep_7h
```

망막병증만 `C_peptide`, `HOMA_IR`, `HOMA_beta`, `BMI_HOMA_IR` 4개를 더해 42개를 쓴다.

### 자동 계산되는 값

병원은 실측값만 넣고, 아래는 백엔드가 만든다. **모든 경로(업로드·직접입력·수정)가
`backend/services/derived.py :: compute_derived` 한 곳을 지난다.**

| 값 | 계산 |
|---|---|
| `age` | 생년월일 + 검사일 → 만 나이 |
| `BMI` | 몸무게 / (키/100)² |
| `LDL` | 실측 우선, 없으면 Friedewald (`chol − HDL − TG/5`) |
| `non_HDL` | `chol − HDL` |
| `eGFR` | CKD-EPI (Cr, 나이, 성별) |
| `TyG_index` | `ln(TG × glu / 2)` |
| `HOMA_IR` / `HOMA_beta` | C-peptide 기반 |
| `DM_duration` | `age − 진단나이` |
| `pulse_pressure` | `SBP − DBP` |
| 소변 dipstick 양성 | 원시값 ≥ 2 |
| `sleep_7h` | 수면시간 ≥ 7 |

> C-peptide 는 병원 측정값을 **변환 없이 그대로** 쓴다.

### 임상 안전망

모델 확률과 별개로, 명백한 임상 위험은 등급의 하한을 강제한다
(예: HbA1c ≥ 11% → 고위험, C-peptide < 1.0 → 중위험 이상, eGFR 저하, LDL ≥ 190, 중증 고혈압).

이 규칙으로 등급이 정해진 경우, 화면의 '1순위 위험 요인'도 그 변수로 바뀌고
값 옆에 기준이 함께 표시된다 (`당화혈색소 15.7% (기준 11% 초과)`).
같은 나이인데 등급이 달라 보이는 상황을 막기 위한 처리다.

### 환자별 위험 변수 (SHAP)

'1순위 위험 요인'은 고정된 지표가 아니라 **그 환자의 예측에 실제로 가장 크게 기여한 변수**다
(`backend/ml/contributions.py`).

후보는 **병원이 실제로 측정하는 항목으로 제한**한다. 운동·수면·흡연·음주는 수집률이 0이라
빼 두었다 — 넣으면 결측 보정값이 1순위로 올라와 잘못된 설명이 나간다.

---

## 5. API

응답은 `{"data": ..., "success": true}`, 오류는 `{"error": ..., "detail": ...}` 형식이다.

```
GET    /health
GET    /api/v1/patients                        ?page=&size=&risk_level=&search=
POST   /api/v1/patients
GET    /api/v1/patients/{id}
PATCH  /api/v1/patients/{id}
DELETE /api/v1/patients/{id}
GET    /api/v1/patients/{id}/visits             방문 이력
GET    /api/v1/patients/{id}/integrated-report  통합 리포트
GET    /api/v1/patients/backup                  전체 백업 CSV
GET    /api/v1/patients/by-chart/{chart_no}
POST   /api/v1/upload/csv
GET    /api/v1/upload/template                  입력 양식 CSV (코드에서 생성)
POST   /api/v1/predict
POST   /api/v1/predict/simulate
POST   /api/v1/scenario/simulate                방치 / 집중관리 시나리오
GET    /api/v1/case-comparison/{id}             유사 사례 3건
POST   /api/v1/graduates/upload                 졸업자 엑셀 (전체 교체)
GET    /api/v1/graduates/count
GET    /api/v1/diagnostics
```

개발 서버 실행 중에는 `http://localhost:8000/docs` 에서 직접 호출해 볼 수 있다.

---

## 6. 설치 파일(.exe) 빌드

**macOS·Linux 에서는 Windows 설치 파일을 만들 수 없다.** PyInstaller 와 Tauri 가
크로스 컴파일을 지원하지 않는다. GitHub Actions 의 Windows 러너에서만 빌드된다.

```bash
# 1) 버전을 세 곳에서 동일하게 올린다
#    backend/main.py (2곳) · frontend/package.json · src-tauri/tauri.conf.json

git commit -am "..." && git push origin main
git tag -a v2.4.2 -m "설명"
git push origin v2.4.2          # ← 태그 push 가 빌드를 트리거한다
```

약 50분 뒤 Releases 에 `.exe`(NSIS, 약 440MB)와 `.msi`(약 590MB)가 게시된다.
진행 상황은 저장소 **Actions** 탭에서 볼 수 있다.

> - 태그 push 후 run 생성까지 3~4분 걸린다. 그 전에 수동 실행하면 동시성 규칙으로
>   서로 취소되니 기다린다.
> - 빌드마다 1GB 넘게 쌓이므로 구버전 Release 는 주기적으로 지운다.

---

## 7. 구조와 유의점

```
backend/            FastAPI 서버
  main.py             진입점 · 라우터 등록 · 정적 파일 서빙
  models/             database.py(ORM·마이그레이션) · schemas.py(API 스키마)
  routers/            patients · upload · prediction · scenario ·
                      case_comparison · graduates · export
  services/           derived.py(파생값 단일 소스) · graduates.py · export_csv.py
  ml/                 predictor.py(예측) · contributions.py(SHAP) · models/*.pkl
  tests/              회귀 테스트
frontend/           React + Vite + Tailwind
  src/pages/          화면별 컴포넌트
  src/components/     RiskCard · RiskGauge · RadarChart · TrendChart 등
  src/api/client.js   백엔드 호출
src-tauri/          데스크톱 셸 — 백엔드 exe 를 sidecar 로 실행
.github/workflows/  Windows 설치 파일 자동 빌드
dbcare-backend.spec PyInstaller 설정 (backend/ + frontend/dist 를 번들)
```

고칠 때 알아야 할 것들:

- **파생값은 `services/derived.py::compute_derived` 만 지난다.** 우회해서 직접 계산하면
  업로드와 직접입력의 결과가 달라진다.
- **`CLINICAL_RANGES`(derived.py) 와 `PatientBase` 의 Field 제약(schemas.py) 은 값이 같아야 한다.**
  CSV 업로드는 Pydantic 을 거치지 않으므로 두 곳 모두에서 막아야 한다.
  어긋나면 `test_clinical_ranges_sync` 가 실패한다.
- **조회 응답 스키마(`PatientResponse`)는 제약을 일부러 느슨하게 뒀다.** 구버전이 저장한
  이상값 하나 때문에 환자 상세가 통째로 500 나던 사고가 있었다.
- **DB 스키마 변경은 `apply_lightweight_migrations()` 에 추가한다** (`PRAGMA user_version` 으로
  중복 실행을 막는다). 이미 설치된 병원 PC 의 데이터를 유지하면서 올려야 한다.
- **유사사례의 합병증 위험도는 입력값이 아니다.** 졸업자 검사수치를 ML 에 넣어 산출한다
  (`services/graduates.py`).
- **환자 데이터는 저장소에 넣지 않는다.** 실명·차트번호·연락처가 들어간 파일은
  `.gitignore` 로 막아 두었다.
