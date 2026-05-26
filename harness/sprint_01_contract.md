# Sprint 1 계약: 백엔드 기반 + ML 예측 API

## 목표
FastAPI 백엔드 완전한 골격 구축.
ML pkl 모델 로딩 및 예측 API, 시나리오 API, 유사 사례 API 구현.
SQLite 데이터베이스 연결 및 환자 스키마 정의.

---

## 구현 항목

### 1. 프로젝트 초기화
- [ ] `backend/requirements.txt`
  ```
  fastapi uvicorn sqlalchemy pydantic python-multipart
  joblib scikit-learn pandas numpy python-dotenv
  ```
- [ ] `backend/main.py` — FastAPI 앱 + CORS(localhost:5173) + 라우터 등록
- [ ] `/health` 엔드포인트

### 2. 데이터베이스 (backend/models/database.py)
Patient 테이블:
```
id, name, chart_no, dob, sex, age, phone,
hba1c, c_peptide, fbg,
ggt, alt, ast, cr,
total_cholesterol, triglycerides, hdl, ldl,
sbp, dbp, bmi,
upload_date
```
측정값 이력 테이블 (MeasurementHistory):
```
id, patient_id, measured_at, c_peptide, hba1c, cr
```
(PatientDetail 추이 차트용)

### 3. 환자 CRUD (backend/routers/patients.py)
- [ ] `GET  /api/v1/patients` — 목록 (page, size, risk_level, search 쿼리 파라미터)
  - `search` 파라미터: name, chart_no, **phone** 컬럼을 OR 조건 LIKE 검색
- [ ] `GET  /api/v1/patients/{id}` — 상세
- [ ] `POST /api/v1/patients` — 생성
- [ ] 시드 데이터: 환자 10명 + 각 6개월 측정 이력 자동 생성

### 4. ML 예측 (backend/ml/predictor.py + backend/routers/prediction.py)
- [ ] pkl 파일 로딩 (없으면 더미 예측값 fallback)
- [ ] `POST /api/v1/predict` — 6개 알고리즘 전체 예측
  ```json
  응답:
  {
    "data": {
      "kidney_disease":   {"score": 72.4, "level": "고위험", "available": true},
      "retinopathy":      {"score": 45.1, "level": "중위험", "available": true},
      "neuropathy":       {"score": 28.3, "level": "저위험", "available": true},
      "cardiovascular":   {"score": null, "level": null,   "available": false},
      "dementia":         {"score": null, "level": null,   "available": false},
      "cerebrovascular":  {"score": null, "level": null,   "available": false}
    },
    "success": true
  }
  ```
- [ ] `POST /api/v1/predict/simulate` — c_peptide, hba1c 값만 바꿔 재예측
  payload: `{ patient_id, c_peptide, hba1c }`

### 5. 시나리오 시뮬레이션 (backend/routers/scenario.py)
- [ ] `POST /api/v1/scenario/simulate`
  payload: `{ patient_id, c_peptide, hba1c }`
  ```json
  응답:
  {
    "data": {
      "radar": {
        "kidney": 72, "cardio": 45, "cerebro": 38,
        "dementia": 52, "retina": 29, "neuro": 61
      },
      "neglect": {
        "life_expectancy": 64,
        "annual_cost_man": 1240,
        "cost_increase_pct": 82,
        "drug_count_before": 1,
        "drug_count_after": 3,
        "insulin_probability": 67,
        "complications": {
          "kidney": "고위험", "cardio": "중위험", "cerebro": "중위험",
          "dementia": "중위험", "retina": "고위험", "neuro": "고위험"
        },
        "symptoms": ["잦은 피로감과 팔인 붓기의 급격한 체중 감소", "시력 저하 및 눈앞에 별빛가 다니는 듯한 증상 (비문증)", "발끝이 부드러지게 따끔따끔한 통증 빈도 증가", "소변에 거품이 많이 생기고 손발 부종 발생"]
      },
      "intensive": {
        "life_expectancy": 78,
        "annual_cost_man": 320,
        "cost_decrease_pct": 42,
        "hba1c_before": 7.2,
        "hba1c_after": 6.3,
        "cpeptide_before": 1.8,
        "cpeptide_after": 3.2,
        "complications": {
          "kidney": "저위험", "cardio": "저위험", "cerebro": "저위험",
          "dementia": "저위험", "retina": "저위험", "neuro": "저위험"
        },
        "improvements": ["아침 기상 시 컨디션이 눈에 띄게 상쾌해짐", "식후 졸음 부담 없이 가볍게 견뎌짐", "시야가 더 또렷해지고 안구 건조감 완화", "손발 저림 증상 완화 및 운동 능력 향상"]
      },
      "recommended_program": {
        "name": "Neuropathy Guard",
        "description": "중위험군 신경병증 진행 차단을 위한 12주 집중 케어"
      }
    },
    "success": true
  }
  ```
  ※ 시나리오 계산 로직: c_peptide, hba1c 슬라이더 값으로 위험도를 선형 보정하여 계산.
  실제 pkl 예측값 기반으로 방치 시는 악화, 집중관리 시는 개선 방향으로 계산.

### 6. 유사 사례 (backend/routers/case_comparison.py)
- [ ] `GET /api/v1/case-comparison/{patient_id}`
  유사도 상위 3개 케이스 반환 (더미 데이터 하드코딩):
  - 유사도%, 나이, 성별, 진단년차, HbA1c 변화, 치료기간
  - 6개 합병증 이전/이후 위험도
  - 예상 의료비 절감, 기대 건강수명

---

## 검증 기준

| # | 기준 | 방법 |
|---|------|------|
| 1 | 서버 포트 8000 정상 실행 | `curl http://localhost:8000/health` → 200 |
| 2 | predict API 6개 항목 반환 | POST /api/v1/predict 호출 |
| 3 | simulate API 슬라이더 값 반영 | c_peptide 1.0 vs 4.0 결과 다름 확인 |
| 4 | scenario API 두 시나리오 반환 | neglect, intensive 키 모두 존재 |
| 5 | case-comparison API 3개 케이스 | 배열 길이 3 확인 |
| 6 | 환자 목록 페이지네이션 | GET /api/v1/patients?page=1&size=8 |
| 7 | pkl 없을 때 앱 크래시 없음 | 모델 파일 없는 상태 예측 요청 |
| 8 | CORS 허용 | OPTIONS 요청 → 200 |

## 완료 정의
8개 기준 모두 PASS. 실패 시 evaluator 피드백 후 재구현.

## 하드 임계값
- API 응답 시간: 3초 이내
- 앱 크래시: 0건
- 필수 엔드포인트 누락: 즉시 실패
