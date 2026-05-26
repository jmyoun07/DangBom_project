# DB-care 프로젝트 마스터 지침 (v2 — Visily UI 기준)

## 프로젝트 개요
병원 내부용 당뇨 합병증 예측 프로그램.
의사가 환자 데이터를 입력하면 6개 ML 알고리즘이 각 합병증 위험도를 예측하고,
슬라이더 시뮬레이션으로 수치 조정 시 미래 위험도·건강수명·의료비 변화를 실시간 비교한다.
현재 3개 알고리즘 완성 (신장질환·망막병증·심혈관), 나머지 3개는 추후 연동 예정.

## 핵심 가치
1. **경각심 유발**: 치료 방치 vs 집중관리 시나리오 비교로 환자가 행동하게 만든다
2. **실시간 시뮬레이션**: C-peptide·HbA1c 슬라이더 → 즉각 위험도·수명·의료비 변화
3. **유사 사례 신뢰성**: 비슷한 환자가 관리로 좋아진 실제 사례 제시로 병원 신뢰도 향상

## 기술 스택
- Backend : FastAPI (Python 3.11+)
- Frontend: React 18 + Vite + TailwindCSS + Recharts
- Database: SQLite (SQLAlchemy ORM)
- ML     : joblib로 pkl 로드, scikit-learn

## 전체 페이지 목록 (6개)

| 경로 | 페이지 | 파일명 |
|------|--------|--------|
| /home | CSV 업로드 | Home.jsx |
| /dashboard/:patientId | 환자 대시보드 | Dashboard.jsx |
| /patients | 환자 목록 | PatientList.jsx |
| /patients/:id | 환자 상세 | PatientDetail.jsx |
| /risk-analysis/:patientId | 시나리오 분석 | RiskAnalysis.jsx |
| /case-comparison/:patientId | 유사 사례 비교 | CaseComparison.jsx |

## 프로젝트 파일 구조
```
db-care/
├── CLAUDE.md
├── harness/
│   ├── orchestrator.py
│   ├── sprint_status.md
│   └── sprint_0X_contract.md
├── backend/
│   ├── main.py
│   ├── models/
│   │   ├── database.py
│   │   └── schemas.py
│   ├── routers/
│   │   ├── patients.py
│   │   ├── prediction.py
│   │   ├── scenario.py
│   │   ├── case_comparison.py
│   │   └── upload.py
│   ├── ml/
│   │   ├── predictor.py
│   │   └── models/          ← .pkl 파일 위치
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Home.jsx
    │   │   ├── Dashboard.jsx
    │   │   ├── PatientList.jsx
    │   │   ├── PatientDetail.jsx
    │   │   ├── RiskAnalysis.jsx
    │   │   └── CaseComparison.jsx
    │   ├── components/
    │   │   ├── layout/
    │   │   │   ├── Sidebar.jsx
    │   │   │   └── Header.jsx
    │   │   ├── RiskGauge.jsx
    │   │   ├── RiskCard.jsx
    │   │   ├── RiskBadge.jsx
    │   │   ├── RiskBar.jsx
    │   │   ├── RadarChart.jsx
    │   │   └── TrendChart.jsx
    │   └── api/
    │       └── client.js
    └── package.json
```

## 페이지별 UI 상세 스펙

---

### 📄 PAGE 1: Home — CSV 데이터 업로드
- 드래그&드롭 업로드 영역 + "파일 선택" 버튼
- "예시 CSV 템플릿 다운로드" 버튼 (핑크 outline)
- 선택된 파일명 표시 (아이콘 + 텍스트)
- **매핑 미리보기 테이블**: CSV 컬럼명 → DB 필드명 → 상태
- **유효성 검사 피드백 패널**: 경고/에러/성공 항목별 리스트
  - 빨강 경고 아이콘: 날짜 형식 오류, 값 범위 초과 등
  - 파란 정보 아이콘: 매핑 성공
  - 주황 에러 아이콘: 필수 컬럼 누락
- "데이터 처리 및 프로필 생성" 버튼 (보라색 primary, 하단 중앙)

---

### 📄 PAGE 2: Dashboard — 환자 대시보드
레이아웃: 3열 (좌측 카드 영역 / 중앙 합병증 그리드 / 우측 분석 패널)

**좌측 상단 — 환자 정보 카드:**
- 이름 이니셜 아바타 (보라색 원)
- 이름 + 성별/나이 배지 (예: M / 64)
- 차트 번호
- 4개 요약 수치: HbA1c / 혈압 / 기간 / 최근평가일

**좌측 중단 — CRITICAL STATUS 게이지:**
- "합병증 고위험 단계" 타이틀 (빨강)
- 경고 아이콘 (우측)
- SVG 반원형 게이지 (고위험=빨강, 중위험=주황, 저위험=초록)
- 중앙 텍스트: "고위험" / "중위험" / "저위험"
- 설명 문구: "현재 합병증 발생 가능성이 매우 높음으로 식별되었습니다."

**좌측 하단 — C-peptide 수치 추이:**
- Recharts LineChart (파란 선, 원형 포인트)
- 현재 수치 우측 상단 (파란색 강조, 예: 4.2 ng/mL)
- X축: 월별 (9월~1월)

**중앙 — 영역별 합병증 상태 (2×3 그리드):**
6개 카드, 각 카드 구성:
  - 아이콘 + 합병증명(한글 굵게) + 영문명(소문자)
  - 위험도 배지 (고위험/중위험/저위험)
  - 핵심 지표명 + 수치 (굵게)
  - 컬러 진행 바 (위험도 색상)

| 카드 | 표시 지표 |
|------|----------|
| 당뇨병성 신장질환 KIDNEY DISEASE | eGFR (mL) |
| 당뇨병성 치매 DIABETES-RELATED DEMENTIA | 나이 (세) |
| 당뇨병성 심혈관 질환 CARDIOVASCULAR | 수축기 혈압 (mmHg) |
| 당뇨병성 신경병증 NEUROPATHY | HDL 콜레스테롤 (mg/dL) |
| 당뇨병성 뇌혈관 질환 CEREBROVASCULAR DISEASE | BMI (kg/m²) |
| 당뇨병성 망막병증 RETINOPATHY | 위험 점수 (안정/주의/위험) |

미완성 알고리즘(심혈관·치매·뇌혈관): 위험도 배지 없이 "준비 중" 표시

**우측 상단 — 주요 위험 요인 분석 패널:**
변수 7개를 수치 + 컬러 바로 수직 나열:
C-peptide (ng/mL) / HbA1c (%) / U-ACR (mg/g) / SBP (mmHg) / BMI (kg/m²) / eGFR (mL) / 나이 (세)

**우측 하단 — 합병증 위험 분석 CTA 카드:**
- 차트 아이콘 (보라색)
- "합병증 위험 분석" 타이틀
- 설명 텍스트
- "Risk Analysis 바로가기 →" 버튼 (보라색 primary)

---

### 📄 PAGE 3: PatientList — 환자 목록 관리
- 상단: 검색창 + 필터(위험도 드롭다운 + 날짜 선택 + 필터 아이콘)
- **검색 범위: 이름, 차트번호, 연락처 동시 검색** (placeholder: "이름, 차트번호 또는 연락처로 검색...")
  - API 쿼리 파라미터 `search=` 에 입력값 전달
  - 백엔드에서 name LIKE / chart_no LIKE / phone LIKE 모두 OR 조건으로 처리
- 테이블 컬럼: 이름 / 차트번호 / 나이 / 성별 / 업로드일 / 위험도(배지) / 관리(상세보기>)
- 페이지네이션: 8명씩, 이전/1/2/3.../다음
- 하단: "전체 X명 중 1-8 표시 중" 텍스트
- 하단 푸터: 이용약관 / 개인정보처리방침 / 도움말

---

### 📄 PAGE 4: PatientDetail — 환자 상세 정보
**상단 네비게이션:**
- "< 환자 목록으로 돌아가기" 링크
- "환자명 환자 상세 정보" 타이틀
- 우측: "데이터 수정" 버튼 + "결과 리포트 출력" 버튼(primary)

**좌측 — 기본 정보 카드:**
- 보라색 원형 아바타
- 이름 + 차트번호 (CN-XXXX-XXXX)
- 생년월일, 나이/성별, 연락처, 최근 내원일

**우측 상단 — AI 합병증 예측 결과:**
- "AI 분석 완료" 배지 (보라색)
- 완성된 알고리즘만 카드 표시 (각 카드: 합병증명 + 위험도 배지 + 위험지수 XX/100 + 빨강 진행 바)

**우측 중단 — 수치 추이 차트 3개:**
C-peptide (ng/mL) / HbA1c (%) / CR 크레아티닌 (mg/dL)
각각 Recharts LineChart, 6개월 추이

**하단 — 최근 검사 수치 테이블 (2열, 한의원 검사 항목 기준):**
아래 14개 항목을 순서대로 좌열 7개 / 우열 7개로 분할 표시:

| 순서 | 항목명 | 단위 | 열 |
|------|--------|------|----|
| 1 | 당화혈색소 (HbA1c) | % | 좌 |
| 2 | C-peptide | ng/mL | 좌 |
| 3 | 공복혈당 | mg/dL | 좌 |
| 4 | GGT | U/L | 좌 |
| 5 | ALT | U/L | 좌 |
| 6 | AST | U/L | 좌 |
| 7 | Cr (크레아티닌) | mg/dL | 좌 |
| 8 | 총콜레스테롤 | mg/dL | 우 |
| 9 | 중성지방 | mg/dL | 우 |
| 10 | HDL 콜레스테롤 | mg/dL | 우 |
| 11 | LDL 콜레스테롤 | mg/dL | 우 |
| 12 | 수축기혈압 | mmHg | 우 |
| 13 | 이완기혈압 | mmHg | 우 |
| 14 | 체질량지수 (BMI) | kg/m² | 우 |

⚠️ 제외 항목 (검사 수치 아님 또는 한의원 미시행):
- 흡연여부 (검사수치 아님) → 제외
- 당뇨병 이환기간 (검사수치 아님) → 제외
- 혈중요소질소(BUN), 헤모글로빈, 백혈구 수 (한의원 미시행) → 제외

각 행: 변수명 + 수치 + 단위 + 비고(정상=초록, 높음=빨강, 주의=주황, 낮음=파랑)

비고 판정 기준 (참고):
- 당화혈색소: ≤5.6% 정상 / 5.7~6.4% 주의 / ≥6.5% 높음
- 공복혈당: ≤99 정상 / 100~125 주의 / ≥126 높음
- GGT: ≤50 U/L 정상 / 초과 시 높음
- ALT: ≤40 U/L 정상 / 초과 시 높음
- AST: ≤40 U/L 정상 / 초과 시 높음
- Cr: 0.6~1.2 mg/dL 정상 / 초과 시 높음
- 총콜레스테롤: ≤199 정상 / 200~239 주의 / ≥240 높음
- BMI: ≤22.9 정상 / 23~24.9 주의(과체중) / ≥25 높음(비만)

**하단 우측 — CTA 카드:**
"분석 레포트 생성하기 →" 버튼 (primary)

---

### 📄 PAGE 5: RiskAnalysis — 시나리오 기반 합병증 분석 ★ 핵심 페이지

페이지 제목: "시나리오 기반 합병증 분석"
서브헤더: RISK ANALYSIS & SCENARIO PLANNING

**상단 좌측 — 건강 지표 시뮬레이션 패널:**
- 우측 상단 "초기화" 버튼
- 슬라이더 2개:
  1. C-peptide 시뮬레이션 (핵심 지표): 0.5~5.0 ng/mL, step 0.1
  2. 당화혈색소 (HbA1c): 5.0~15.0%, step 0.1
- 슬라이더 현재값 우측에 표시 (파란색 강조)
- Tip 박스: "C-peptide 수치를 1%만 개선해도 합병증 발병 위험이 유의미하게 감소하는 효과가 시뮬레이션 되었습니다."

**상단 우측 — 합병증 리스크 프로필:**
- Recharts RadarChart (6각형)
- 6개 축: 신장질환 / 심혈관 / 뇌혈관 / 치매 / 망막병증 / 신경병증
- 슬라이더 값 변경 시 실시간 업데이트 (300ms debounce)
- 연보라색 채우기

**하단 — 미래 시나리오 분석 결과 (2열):**

🔴 왼쪽 "치료 방치 시" 카드:
- 주황 원형 아이콘 + "치료 방치 시" 제목
- 예상 건강수명: XX세 (빨간 큰 숫자) + "초기 합병증 위험"
- 예상 의료비: X,XXX만 (빨간 큰 숫자) + "현재 대비 +XX% 증가"
- 지표 악화 예측 섹션:
  - 당뇨약 개수: X개 → X개
  - 인슐린 맞을 확률: XX%
- 합병증 위험도 6행 (라벨 + 진행 바):
  당뇨병성 신장질환 / 심혈관 질환 / 뇌혈관 질환 / 치매 / 망막병증 / 신경병증
  (고위험=빨강, 중위험=주황, 저위험=초록)
- 체감되는 전조 증상 bullet list (4~5개)

🟢 오른쪽 "집중관리 시 (6개월 후)" 카드:
- 초록 번개 아이콘 + "집중관리 시 (6개월 후)" 제목
- 예상 건강수명: XX세 (초록 큰 숫자) + "건강수명 연장 예측"
- 예상 의료비: XXX만 (초록 큰 숫자) + "현재 대비 XX% 감소"
- 지표 개선 예측 섹션:
  - 당화혈색소: X.X% → X.X% (초록 화살표)
  - C-peptide: X.X → X.X ng/mL (초록 화살표)
- 합병증 위험도 6행 (모두 저위험=초록 바)
- 기대되는 건강 변화 bullet list (4~5개)

**최하단 — 최적 권장 프로그램 배너:**
- 보라 배경 카드
- DB-care 아이콘 + 프로그램명 (예: Neuropathy Guard)
- 설명 텍스트 + "프로그램 신청 안내 ↗" 버튼 (흰색)

**시뮬레이션 API:**
- 슬라이더 변경 → 300ms debounce → POST /api/v1/scenario/simulate
- payload: { patientId, c_peptide, hba1c }
- response: { radar: {6개 위험도}, neglect: {...}, intensive: {...} }

---

### 📄 PAGE 6: CaseComparison — 유사 사례 분석 결과

페이지 제목: "유사 사례 분석 결과"
부제: "인공지능이 [환자명] 님의 데이터 포인트를 분석하여 최적의 성공 사례를 찾았습니다."
우측 상단: 큰 보라색 "A" 일러스트

**탐색 과정 4단계 수평 스텝퍼:**
- 원형 아이콘 4개 + 연결선 + 완료 체크(✓)
- STEP 01: 데이터 수집 및 정제
- STEP 02: 핵심 특징 추출
- STEP 03: 유사도 알고리즘 가동
- STEP 04: 상위 3개 사례 확정
- 모든 스텝 완료(체크) 상태로 표시

**최적의 매칭 사례 (3개 카드 가로 나열):**
헤더: "최적의 매칭 사례 총 3건" + "정렬 기준: 유사도 순"

각 카드 (3등분 너비):
- 상단: 아바타(어두운 원) + 이름(마스킹: 김*현) + 유사도 XX% 배지(초록) + 추이 아이콘
- 나이·성별·진단 X년차
- HbA1c 변화: X%→X% / 치료 기간: X개월 + "집중케어" 배지(파란)
- 구분선
- "합병증 위험도 변화 (당뇨 프로그램 진/후)" 라벨 + "이전 ● 이후 ●" 범례
- 6개 합병증 행:
  - 합병증명 / XX% 위험도 / 이전 바(빨강) + 이후 바(파랑)
- 구분선
- 예상 의료비 절감: 연 XXX만원 / 기대 건강수명: XX세
- "상세 리포트 보기 >" 링크

**API:**
GET /api/v1/case-comparison/{patientId}
응답: 유사도 상위 3개 케이스 (더미 데이터로 구현)

---

## 공통 디자인 시스템

### 색상 팔레트
```
Primary    : #6366f1 (인디고)   → 버튼, 활성 메뉴, 배지
Danger     : #ef4444 (빨강)    → 고위험
Warning    : #f59e0b (주황)    → 중위험
Success    : #22c55e (초록)    → 저위험
Info       : #3b82f6 (파랑)    → 추이 차트, 데이터 포인트
BG         : #f8f9fc           → 페이지 배경
Card       : #ffffff            → 카드 배경
Sidebar    : #1e1e2e (다크)     → 좌측 사이드바
Text Main  : #111827
Text Sub   : #6b7280
```

### 공통 컴포넌트 Props 규격
```jsx
<RiskBadge level="고위험"|"중위험"|"저위험" />
<RiskBar score={0~100} />
<RiskGauge score={0~100} level="고위험" />   // SVG 반원
<RadarChart data={{kidney, cardio, cerebro, dementia, retina, neuro}} />
<TrendChart data={[{month, value}]} unit="ng/mL" color="#3b82f6" />
```

## ML 모델 현황 (v2.2-debias — 역인과 완화 재학습 완료)
```
완성 (3개):
  retinopathy     → retinopathy_model.pkl  (XGBoost,                  42 feats, HN19-21,       val AUC 0.843)
  kidney_disease  → dkd_model.pkl          (Stacking[XGB+LGB+CB→LR],  38 feats, HN19-24,       val AUC 0.752, sens 0.630, spec 0.694)
  cardiovascular  → cvd_model.pkl          (EasyEnsemble n=50,        38 feats, HN19-21+HN24,  val AUC 0.761, sens 0.667, spec 0.703)

준비 중 (3개):
  neuropathy      → None  (UI: "분석 준비 중")
  dementia        → None
  cerebrovascular → None
```

### v2.2-debias 학습 파이프라인 (DKD / CVD)
- **Optuna 150 trials × {XGBoost, LightGBM, CatBoost}** (TPESampler + MedianPruner + early stopping 30R)
- **Stacking ensemble**: 3 base 모델의 OOF predict_proba → LogisticRegression(class_weight='balanced') meta
- **EasyEnsemble baseline**: n_estimators ∈ {20, 50, 80} 비교
- **Threshold 선정**: Youden's J vs F-beta1.5 비교, sensitivity 우선 자동 채택
- **모델 선정 기준**: 5-fold OOF AUC (validation overfitting 방지)
- **역인과 완화** (insulin_medication, DM_medication 에 3중 처리):
  1. monotonic constraint = +1 (자연적 의학 방향 강제)
  2. feature_weight = 0.5 (XGB tree split 빈도 감소)
  3. sample_weight cap = 0.7 (해당 변수 양성 샘플 가중치 30% 감소)
- 학습 스크립트: `공통_전처리/train_debias_common.py` (DKD/CVD 공유)
- `predictor.py` 는 `model_type=="Stacking"` 일 때 base 3 모델 → meta LR 경로로 예측

### 타겟 정의
```
retinopathy    : DH7_dg == 1  또는 E_DM == 1 (망막병증 의사진단/심각도)
kidney_disease : DN1_dg == 1  (콩팥병 의사진단)        ※ 타겟 누수 방지 위해 HE_crea, eGFR 사용
cardiovascular : DI3_dg / DI4_dg / DI5_dg / DI6_dg 중 하나라도 1
                 (고혈압·이상지질혈증·뇌졸중·심근경색/협심증)
```

### 질환별 변수 구성 (per-disease)
**DR(망막병증)만 C-peptide 4종 포함 (HN22+ 에서는 HE_insulin 측정 중단되어 DKD·CVD 는 제외).**

공통 38 변수:
```
인구통계(2)        : age, sex
당뇨(4)           : DM_duration, DM_diagnosis_age, DM_medication, insulin_medication
혈당(2)           : HE_glu, HE_HbA1c
인슐린 저항성(1)   : TyG_index  (파생: ln(TG × glu / 2))
지질(5)           : HE_chol, HE_HDL_st2, HE_TG, LDL_calc, non_HDL
                   (LDL_calc: 병원 실측치 우선, 미입력시 Friedewald 공식)
신장(2)           : HE_crea, eGFR  (CKD-EPI)
혈압(4)           : SBP, DBP, pulse_pressure, hypertension
신체 계측(3)       : HE_BMI, HE_ht, HE_wt
간효소(2)         : HE_ast, HE_alt
소변 확장(9)       : HE_Upro_pos, HE_Uglu_pos, HE_Ubld_pos,
                    HE_Ubil_pos, HE_Uket_pos, HE_Uro_abn,
                    HE_Unitr_b, HE_Uph, HE_Usg
생활습관(4)        : smoking, drinking, exercise, sleep_7h  (수면 ≥7h binary)
```
DR 전용 추가(4): **C_peptide**, HOMA_IR, HOMA_beta, BMI_HOMA_IR → 합계 42 변수

### C-peptide 기반 재학습 (v2.2)
- KNHANES HE_insulin (µU/mL) 을 **C_peptide (ng/mL) = HE_insulin / 3.0** 으로 변환 후 학습
- HOMA_IR / HOMA_beta / BMI_HOMA_IR 모두 C_peptide 값으로 계산 :
  - `HOMA_IR     = glu × C_peptide / 405`
  - `HOMA_beta   = 360 × C_peptide / (glu - 63)`
  - `BMI_HOMA_IR = BMI × HOMA_IR`
- 병원은 C-peptide 만 측정하므로 **원본값 그대로 전달** (× 3.0 변환 불필요)
- 구 데이터(HE_insulin 만 있는 경우)는 `c_peptide = he_insulin / 3.0` 로 하위호환

### 병원 입력 간소화 (자동 파생)
병원 양식은 원본 측정값만 받고, 다음은 백엔드가 자동 계산:
- **age** : `dob + exam_date` 로부터 만나이 자동 산출 → 병원 입력 불필요
- **BMI** : `weight / (height/100)²`
- **LDL** : 병원 실측 우선, 없으면 Friedewald (`chol - HDL - TG/5`, TG < 400)
- **non_HDL** : `chol - HDL`
- **eGFR** : CKD-EPI (Cr, age, sex)
- **HE_insulin** : `c_peptide × 3.0` (하위호환용 저장만, 모델은 c_peptide 사용)
- **HOMA_IR / HOMA_beta / BMI_HOMA_IR / TyG_index** : 위 공식대로 자동
- **DM_duration** : `age - DM_diagnosis_age`
- **pulse_pressure** : `SBP - DBP`
- **dipstick 양성 binary** (HE_Upro_pos 등): dipstick 원시값 ≥ 2
- **sleep_7h** : `sleep_hours ≥ 7`

단일 소스 모듈: `backend/services/derived.py :: compute_derived(dict) -> dict`
(업로드 / POST / PATCH 모두 동일 경로로 파생값 생성)

### 제거된 변수 (병원 미수집)
HE_BUN, HE_Ualb, HE_Ucrea, ACR, HE_HB, HE_WBC, HE_RBC, HE_wc, dyslipidemia, GGT, visceral_fat

pkl 없을 경우: 더미 예측값 fallback 반환, 앱 크래시 없음.

## API 엔드포인트
```
GET  /health
GET  /api/v1/patients                    ?page=&size=&risk_level=&search=
GET  /api/v1/patients/{id}
POST /api/v1/patients
POST /api/v1/upload/csv
POST /api/v1/predict                     body: {patient_data}
POST /api/v1/predict/simulate            body: {patient_id, c_peptide, hba1c}
POST /api/v1/scenario/simulate           body: {patient_id, c_peptide, hba1c}
GET  /api/v1/case-comparison/{id}
```

## 코딩 원칙
- 응답 형식: `{"data": ..., "success": true}` / `{"error": "...", "detail": "..."}`
- CORS: localhost:5173 허용
- 로딩 상태 반드시 표시 (Spinner 또는 Skeleton)
- 한국어 UI + 영어 코드/변수명
- TailwindCSS 유틸리티 클래스 사용
- 더미 데이터: 실제 의료 수치 범위 내 현실적으로 생성

## 항상 먼저 읽을 것
작업 전 반드시:
1. 이 CLAUDE.md 전체 읽기
2. harness/sprint_status.md 현재 상태 확인
3. 해당 스프린트 계약 파일 읽기

---

## AI 에이전트 협업 규칙 (agent-link MCP)

**목적**: Claude Code가 해결하지 못하는 문제는 다른 AI 코딩 에이전트에게 넘겨 협업한다.

### 설치된 MCP / CLI
- `agent-link-mcp` (v0.5.0) — MCP 서버로 활성화됨
- `codex` CLI (v0.116.0) — 사용 가능
- `gemini` CLI — 미설치 (필요 시 `npm i -g @google/gemini-cli` 후 인증)

### 사용 가능한 MCP 도구
- `mcp__agent-link__spawn_agent` — 다른 에이전트 실행
- `mcp__agent-link__spawn_agents` — 여러 에이전트 병렬 실행
- `mcp__agent-link__reply` — 실행된 에이전트의 질문에 답변
- `mcp__agent-link__kill_agent` — 에이전트 세션 종료
- `mcp__agent-link__list_agents` — 사용 가능한 CLI 확인
- `mcp__agent-link__get_status` — 실행 상태 확인

### 에스컬레이션 규칙 (반드시 준수)

**같은 에러를 2번 연속으로 해결하지 못하면** 즉시 `spawn_agent`로 codex 에이전트를 호출한다.

판정 기준:
1. 동일한 에러 메시지 / 테스트 실패가 Claude Code의 수정 후에도 재발
2. 다른 방향으로 한 번 더 수정했는데 또 같은 에러 발생
3. → 이 시점에서 codex 에스컬레이션 **필수** (더 시도하지 말 것)

### 호출 템플릿

```json
{
  "agent": "codex",
  "task": "<\uBB38\uC81C \uC124\uBA85 + \uBB34\uC5C7\uC744 \uD574\uC57C \uD558\uB294\uC9C0 1\u00B72\uC904>",
  "context": {
    "files": ["<\uAD00\uB828 \uD30C\uC77C \uC808\uB300\uACBD\uB85C>", "..."],
    "error": "<\uC5D0\uB7EC \uC804\uBB38 \uBCF5\uC0AC>",
    "intent": "<\uC774\uC804\uC5D0 \uC2DC\uB3C4\uD55C \uC811\uADFC 2\uAC1C \uC694\uC57D>"
  },
  "model": "gpt-5",
  "thinking": "high",
  "timeoutMs": 600000
}
```

### task 작성 원칙
- 재현 방법, 기대 동작, 실제 동작을 구체적으로 기술
- 이미 시도한 접근 2가지를 명시해 중복 시도 방지
- 건드려도 되는 파일 / 건드리면 안 되는 파일 구분

### context 작성 원칙
- `files`는 절대경로로 전달
- `error`는 전체 스택트레이스 포함
- `intent`는 "왜 이걸 고치려는지" (기능 요구사항 링크)

### 응답 처리
- `status: "done"` → 결과 적용 및 검증
- `status: "waiting_for_reply"` → `reply` 도구로 질문에 답변
- `error` → 원인 파악 후 재시도 또는 사용자 보고

### 병렬 협업 패턴
- 한 기능을 **codex + claude 동시 리뷰**: `spawn_agents`로 병렬 호출
- 한쪽은 버그 찾기, 한쪽은 보안 리뷰 등 역할 분담

### 에스컬레이션 로그
에스컬레이션 발생 시 `harness/agent_escalations.md`에 다음을 기록:
- 날짜/시각, 원본 문제, 시도한 접근 2가지, codex에 전달한 task/context, 최종 해결책
