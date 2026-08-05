# DB-care — 당뇨 합병증 예측 프로그램

병원 내부용 데스크톱 앱. 환자 검사수치를 입력하면 6개 ML 모델이 합병증 위험도를 예측하고,
시나리오 시뮬레이션·유사사례 비교를 제공한다.

- **프로그램 사용법만 필요하다면** → [설치 및 사용](#설치-병원-담당자용) 만 보면 된다.
- **코드를 유지보수한다면** → [개발 환경](#개발-환경-구축) 부터 읽는다.

---

## 설치 (병원 담당자용)

1. **설치 파일 다운로드** — GitHub Releases 페이지에서 최신 `DB-care_x.y.z_x64-setup.exe`
2. 실행 → 설치 마법사 진행 → 바탕화면 아이콘으로 실행
3. **졸업자 데이터 업로드** (유사사례 기능에 필요, 최초 1회)
   - 프로그램 → **설정(Settings)** → **졸업자 엑셀 업로드**
   - `docs/병원배포/졸업자_임상데이터_업로드용.xlsx` 선택
   - "졸업자 N명 데이터를 불러왔습니다" 확인
4. **환자 데이터 업로드** — 홈 화면에서 CSV/엑셀 업로드, 또는 "한 명 직접 입력"

### 데이터가 저장되는 위치

| OS | 경로 |
|---|---|
| Windows | `%APPDATA%\DB-care\dbcare.db` |
| macOS | `~/Library/Application Support/DB-care/dbcare.db` |

프로그램을 재설치해도 이 파일은 유지된다. **백업은 설정 → 전체 환자 데이터 백업(CSV)** 으로 받는다.
오류 로그는 같은 폴더의 `backend.log` 에 쌓인다 — 문제 발생 시 이 파일을 확인한다.

### 졸업자 데이터 갱신

새 졸업자가 생기면 `docs/병원배포/졸업자_RAW_데이터셋_양식_병원발송용.xlsx` 양식으로 채워
설정에서 다시 업로드한다. **업로드는 전체 교체이므로 항상 전체 명단이 담긴 파일을 올린다.**
양식 파일의 '코딩북'·'작성방법' 시트에 항목별 입력 규칙이 있다.

---

## 개발 환경 구축

### 요구 버전 (중요)

| 도구 | 버전 | 비고 |
|---|---|---|
| **Python** | **3.11** | ⚠️ 3.9/3.10 은 `shap` 설치 실패. 3.12+ 는 미검증 |
| **Node.js** | **20.19 이상** | Vite 8 요구 사항 |
| Rust | stable (MSVC) | Windows 설치 파일 빌드 시에만 필요 |

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

`DBCARE_DB_PATH` 환경변수로 DB 파일 위치를 바꿀 수 있다(테스트용 빈 DB 등).
`DBCARE_SEED=1` 로 기동하면 시연용 시드 환자 10명이 생성된다.

### 테스트

```bash
cd backend
PYTHONPATH=. .venv/bin/python tests/test_contributions.py     # 개별 실행
for t in tests/*.py; do PYTHONPATH=. .venv/bin/python "$t"; done   # 전체
```

배포 전 전체 점검은 `scripts/qa_smoke.py` — 빈 DB 로 서버를 띄운 뒤 실행하면
병원 실제 업무 흐름 47개 항목을 검증한다.

---

## 설치 파일(.exe) 빌드

**macOS/Linux 에서는 Windows 설치 파일을 만들 수 없다.** PyInstaller·Tauri 가 크로스 컴파일을
지원하지 않기 때문이다. GitHub Actions 의 Windows 러너에서만 빌드된다.

```bash
# 버전 올리기 — 아래 3개 파일의 버전을 동일하게 맞춘다
#   backend/main.py (2곳)  /  frontend/package.json  /  src-tauri/tauri.conf.json

git commit -am "..." && git push origin main
git tag -a v2.4.2 -m "설명"
git push origin v2.4.2          # ← 태그 push 가 빌드를 트리거한다
```

약 50분 뒤 GitHub Releases 에 `.exe`(NSIS)와 `.msi` 가 자동 게시된다.
진행 상황은 저장소의 **Actions** 탭에서 볼 수 있다.

> **주의**
> - 태그를 push 한 뒤 run 생성까지 3~4분 걸린다. 그 전에 수동 실행하면 동시성 규칙으로
>   서로 취소되니 기다린다.
> - 빌드마다 Release 약 1GB + 아티팩트 약 1GB 가 쌓인다. 저장소 용량 관리를 위해
>   구버전 Release 는 주기적으로 삭제한다.

---

## 구조

```
backend/          FastAPI 서버
  main.py           앱 진입점·라우터 등록·에러 규격
  models/           DB 모델(database.py)·API 스키마(schemas.py)
  routers/          patients · upload · prediction · scenario · case_comparison · graduates
  services/         derived.py(파생변수 단일 소스) · graduates.py · export_csv.py
  ml/               predictor.py(6개 모델 예측) · contributions.py(SHAP) · models/*.pkl
  tests/            회귀 테스트 (배포 전 전체 통과 필수)
frontend/         React 18 + Vite + Tailwind
  src/pages/        Home · Dashboard · PatientList · PatientDetail · RiskAnalysis ·
                    CaseComparison · ExamHistory · IntegratedReport · Settings
src-tauri/        데스크톱 셸(Tauri) — 백엔드 exe 를 sidecar 로 실행
scripts/          양식 생성·데이터 변환·QA 스크립트
docs/병원배포/     병원에 전달하는 졸업자 데이터·입력 양식
CLAUDE.md         상세 스펙 — 화면 구성, ML 변수 정의, API 규격
```

### 알아둘 설계 포인트

- **파생변수는 `services/derived.py::compute_derived` 단일 경로**로만 계산한다.
  업로드·수기등록·수정이 모두 이 함수를 거친다. 여기를 우회하면 값이 어긋난다.
- **`CLINICAL_RANGES`(derived.py) 와 `PatientBase` Field 제약(schemas.py) 은 값이 같아야 한다.**
  어긋나면 `tests/test_clinical_ranges_sync.py` 가 실패한다. CSV 업로드는 Pydantic 을
  거치지 않으므로 두 곳 모두에서 막아야 한다.
- **조회 응답 스키마(`PatientResponse`)는 제약을 완화해 둔다.** 구버전이 저장한 이상값
  때문에 환자 상세가 통째로 500 나던 사고가 있었다(`tests/test_legacy_value_resilience.py`).
- **합병증 위험도는 병원이 입력하는 값이 아니다.** 졸업자 raw 데이터의 검사수치를
  ML 에 넣어 자동 산출한다(`services/graduates.py::_predict_comp`).
- **SHAP 기여도는 병원이 실제 측정하는 변수로만 계산한다**(`ml/contributions.py`).
  운동·수면·흡연은 수집률 0이라 후보에서 제외 — 넣으면 imputer 가 채운 값이 1순위가 된다.

---

## 이관 시 함께 받아야 할 것

이 저장소에 **없는** 것들:

- **환자 데이터** — 개인정보라 소스에 포함하지 않는다. 기존 PC 에서 설정 → 백업(CSV) 으로
  내려받아 옮기거나, 새로 업로드한다.
- **ML 학습 원시데이터** — 국민건강영양조사(KNHANES) 원본은 재배포 제한이 있어 제외했다.
  모델 재학습이 필요하면 KNHANES 를 직접 신청해 받아야 한다. 학습된 모델(`.pkl`)은 포함돼 있어
  **예측 사용에는 문제가 없다.**
- **GitHub 저장소 접근 권한** — 빌드(Actions)를 돌리려면 저장소 권한이 필요하다.
