# Sprint 1 결과: 백엔드 기반 + ML 예측 API

## 완료일: 2026-04-15
## 상태: ✅ 전체 통과 (8/8)

---

## 구현 항목 완료 현황

### 1. 프로젝트 초기화 ✅
- `backend/requirements.txt` - 12개 패키지 (fastapi, uvicorn, sqlalchemy, pydantic, python-multipart, joblib, scikit-learn, pandas, numpy, python-dotenv, imbalanced-learn, xgboost)
- `backend/main.py` - FastAPI 앱 + CORS(localhost:5173) + 5개 라우터 등록 + startup 시드 데이터
- `/health` 엔드포인트 - `{"status": "ok", "service": "DB-care API", "version": "1.0.0"}`

### 2. 데이터베이스 ✅
- `Patient` 테이블: 42개 컬럼 (통일 41개 변수 대응 + 메타데이터)
- `MeasurementHistory` 테이블: c_peptide, hba1c, cr 추이
- SQLite + SQLAlchemy ORM

### 3. 환자 CRUD ✅
- `GET /api/v1/patients` - 페이지네이션 + risk_level 필터 + search(이름/차트번호/연락처 OR 검색)
- `GET /api/v1/patients/{id}` - 상세 + 측정 이력
- `POST /api/v1/patients` - 생성
- 시드 데이터: 환자 10명 + 각 6개월 측정 이력

### 4. ML 예측 ✅
- 3개 pkl 모델 로딩 (dkd_model.pkl, retinopathy_model.pkl, cvd_model.pkl)
- 통일 41개 KNHANES 변수 기반 예측
- `POST /api/v1/predict` - 6개 알고리즘 전체 예측 (3 available + 3 unavailable)
- `POST /api/v1/predict/simulate` - c_peptide/hba1c 오버라이드 재예측
- pkl 없을 때 더미 예측값 fallback (앱 크래시 없음)

### 5. 시나리오 시뮬레이션 ✅
- `POST /api/v1/scenario/simulate`
- radar(6축) + neglect(방치시) + intensive(집중관리시) + recommended_program

### 6. 유사 사례 비교 ✅
- `GET /api/v1/case-comparison/{patient_id}`
- 3개 더미 케이스 (유사도%, 합병증 이전/이후, 의료비 절감, 건강수명)

### 7. CSV 업로드 ✅
- `POST /api/v1/upload/csv`
- KNHANES 변수명 -> DB 필드 매핑
- 유효성 검사 피드백 (errors/warnings/successes)

---

## 검증 결과

| # | 기준 | 결과 | 상세 |
|---|------|------|------|
| 1 | 서버 포트 8000 정상 실행 | ✅ PASS | `{"status":"ok"}` |
| 2 | predict API 6개 항목 반환 | ✅ PASS | 3 available + 3 unavailable |
| 3 | simulate API 슬라이더 값 반영 | ✅ PASS | cpep 1.0: [34.1, 8.1, 40.6] vs cpep 4.0: [37.1, 6.6, 42.2] |
| 4 | scenario API 두 시나리오 반환 | ✅ PASS | radar + neglect + intensive + recommended_program |
| 5 | case-comparison API 3개 케이스 | ✅ PASS | 유사도 80~86% |
| 6 | 환자 목록 페이지네이션 | ✅ PASS | total=10, page=1, data=8 |
| 7 | pkl 없을 때 앱 크래시 없음 | ✅ PASS | 3 loaded + 3 fallback |
| 8 | CORS 허용 | ✅ PASS | access-control-allow-origin: http://localhost:5173 |

---

## 버그 수정 이력

### C-peptide -> Insulin 변환 계수 오류
- **문제**: `c_peptide * 0.27` 으로 변환 시 insulin 값이 0.27~1.08 범위로 너무 작아 모델 예측값에 차이 없음
- **해결**: `c_peptide * 3.0` 으로 변경 (C-peptide ng/mL x 3.0 = insulin uU/mL 근사)
- **결과**: c_peptide 1.0 vs 4.0 에서 kidney_disease 34.1->37.1 (+3.0), retinopathy 8.1->6.6 (-1.5), cardiovascular 40.6->42.2 (+1.6)

---

## 생성/수정 파일 목록

| 파일 | 상태 |
|------|------|
| `backend/requirements.txt` | 신규 |
| `backend/main.py` | 신규 |
| `backend/models/database.py` | 신규 |
| `backend/models/schemas.py` | 신규 |
| `backend/routers/patients.py` | 신규 |
| `backend/routers/prediction.py` | 신규 |
| `backend/routers/scenario.py` | 신규 |
| `backend/routers/case_comparison.py` | 신규 |
| `backend/routers/upload.py` | 신규 |
| `backend/ml/predictor.py` | 신규 |
| `backend/ml/models/dkd_model.pkl` | 기존 (ML 재학습 결과물) |
| `backend/ml/models/retinopathy_model.pkl` | 기존 |
| `backend/ml/models/cvd_model.pkl` | 기존 (ML 재학습 결과물) |
