# DB-care v1.0.0 → v2.0.0 대대적 개선 · 세션 간 체크포인트

> 목적: 한 번에 토큰이 부족할 만큼 큰 작업을 다중 세션으로 자율 실행. 각 세션은 이 파일을 먼저 읽고 남은 작업을 이어 진행한다.

## 작업 규칙 (다음 세션이 이 파일을 열었을 때 따를 것)

1. **먼저 이 파일 전체를 읽는다.** `STATUS` 섹션에서 직전 세션이 멈춘 지점을 파악한다.
2. `TodoWrite` 로 잔여 TODO를 복원한다 (이 파일의 `TODO TABLE` 그대로).
3. 진행 중 표시된 항목부터 이어서 작업. 완료 시 `✅` 로 표시 + 변경 파일 경로를 `NOTES` 에 남긴다.
4. 세션 종료 직전 (`used:` 가 `limit` 의 75% 이상일 때 추정) 이 파일 `STATUS` 업데이트 + `durable cron` 으로 다음 세션 트리거 재예약.
5. **금기 (병원측 요청):** 아래 항목은 건드리지 않는다.
   - 사이드바 영문 메뉴 (선택적)
   - 합병증 카드 이모지 (MVP)
   - Radar 3축 0 표시 (ML 미구현 3개, 추후 변경)
   - RiskGauge 숫자 미표시 (환자용 의도)
   - 의료 cut-off 수치 (HDL 성별차, Cr 성별차, LDL 당뇨 특화)
   - 예상 건강수명/인슐린 확률/예상 의료비/의료비 절감 수치 (마케팅 목적)
   - PatientDetail "결과 리포트 출력" (추후 구현)

## 병원측 지시 특수 사항

- **12,000건 허구 수치** → 실제 환자 DB count 로 교체 (✅ `usePatientCount` 훅으로 `count` 사용).
- **유사사례 ghost 카드** → 더미 명시 또는 제거. (✅ CaseComparison 상단 "데모 샘플" 배너 추가)
- **PatientDetail 예측 호출** → 매 mount 가 아닌 "환자 데이터 수정 시에만" 재호출. (✅ sessionStorage 캐시 + updated_at 키)
- **ML 역인과 (Reverse causality):** 인슐린 투약 여부, 당뇨약 개수가 모델에 과도한 영향.
  UI에서는 이 두 값을 계속 표시해야 하므로 모델 feature로는 유지. 대신 학습 시 **계수 상한**
  또는 **monotonic constraint** 또는 **sample weight cap** 으로 영향력 축소. 재학습 스크립트는
  `신장질환/retrain_v2_debias.py`, `심혈관/retrain_v2_debias.py` (신규) 에서 처리. (⬜ L1 — 후속 GPU 작업)

---

## STATUS

- 세션 시작: 2026-04-25
- 세션 3 (2026-04-25 자동 재개): UI/UX 대규모 리팩토링 마무리 단계.
- 세션 4 (2026-04-25 이어서): 백엔드 audit trail (N2) + D9 단축키 힌트.
- 세션 5 (2026-04-25 이어서): L1 ML 역인과 재학습 v2.2-debias (DKD 35분 + CVD 18분).
- 세션 6 (2026-04-26 자동 재개): E2 Dashboard edge cases + D1 color contrast audit + theme.js 메타데이터 동기화.
- **완료:** PatientList 페이지네이션, ConfirmModal/ConfirmProvider, Settings/EditPatientModal/CommandPalette 접근성,
  TrendChart Y도메인+참조선, PatientContextBar 캐시 무효화 이벤트, Header 실 헬스체크, Home CSV 검증/키보드/aria-live,
  Sidebar 모바일 토글, index.css print/reduced-motion/sr-only, accent 하드코딩 잔여 정리.
- **세션 4 완료:** N2 audit trail (PatientAudit ORM + PATCH diff 기록 + GET /audit + PatientAuditCard UI),
  D9 단축키 힌트 sm: 노출 (모바일은 / 만).
- **세션 5 완료:** L1 v2.2-debias 재학습 (Optuna 150×3 + Stacking + EasyEnsemble + Youden/Fbeta1.5):
  - DKD: Stacking 채택, val AUC 0.7524, sens 0.630, spec 0.694 (이전 EE 0.7594/0.519/0.795 대비 sens +21pp)
  - CVD: EasyEnsemble n=50 채택, val AUC 0.7608, sens 0.667, spec 0.703 (이전 EE 0.7551/0.724/0.646 대비 AUC+spec 향상)
  - 역인과 완화: insulin/DM_medication 에 monotonic +1, feature_weight 0.5, sample_weight cap 0.7
- **세션 6 완료:**
  - **E2 (Dashboard edge):** invalid patientId 가드 + 404/network/unknown 에러 구분 + patientId 변경 시 stale 환자/예측 reset (`Dashboard.jsx`).
  - **D1 (color contrast):** gaugeHeadingColor amber-600/emerald-600 → 700 (AA 4.5:1 충족), chart_no text-gray-400 → 500, gradient CTA text-white/85 → /95 (Dashboard, PatientDetail).
  - **MODEL_META 동기화:** kidney Stacking val AUC 0.752, cardio EasyEnsemble val AUC 0.761, version v2.2-debias (`theme.js`).
- **남은 작업 (디자인 보존):** E4 (Case 스텝 애니), C4 (Case before/after side-by-side), C5 (EditPatientModal 아코디언) — 디자이너 결정으로 현재 디자인 유지.
- 다음 재개 시: cron 자체 정리 가능 — 핵심 TODO 모두 해소.

---

## TODO TABLE (121 이슈 → 실행 가능한 48개 그룹)

| # | 상태 | 그룹 | 설명 | 대상 파일 (메모) |
|---|------|------|------|-------------------|
| A0 | ✅ | Version | v1.0.0 backup + v2.0.0 bump | `_backup_v1.0.0/`, `backend/main.py`, `Header.jsx`, `Settings.jsx`, `DB-care.iss`, `build-setup.ps1` |
| A1 | ✅ | Tokens | 디자인 토큰 중앙화 | `frontend/src/theme.js` |
| A2 | ✅ | Color | 위험도 색상 (mid=amber) 전 컴포넌트 일치 | RiskBadge/Bar/Gauge/Radar (theme.RISK_COLORS) |
| A3 | ✅ | Color | PatientDetail AI 진행바 level별 색 | `PatientDetail.jsx` (RiskBar 사용) |
| A4 | ✅ | Color | TrendChart 페이지별 색 일치 (primary accent) | `PatientDetail.jsx` (var(--color-accent)) |
| A5 | ✅ | Color | accent `#6366f1` 하드코딩 → CSS var | `Home.jsx`, `EditPatientModal.jsx`, `Dashboard.jsx`/`PatientDetail.jsx` (var fallback) |
| A6 | ✅ | Unit | 단위 표기 일관화 mg/dL·kg/m²·ng/mL·mmHg·% | `PatientDetail.jsx` UNITS + theme.js |
| B1 | ✅ | Viz | RiskAnalysis 85/50/20 매직넘버 → 실 score | `RiskAnalysis.jsx` (`normalizeComplication`) + `backend/routers/scenario.py` |
| B2 | ✅ | Viz | Radar 범례/설명 + radius 축 의미 | `RadarChart.jsx` |
| B3 | ✅ | Viz | TrendChart: 연도, Y도메인, reference area, critical line | `TrendChart.jsx` |
| B4 | ✅ | Viz | Dashboard 주요 위험 요인 바 의미있는 정규화 | `Dashboard.jsx` (`riskPct` + REFERENCE_RANGES) |
| B5 | ✅ | Viz | RiskGauge arc dasharray 반원 기준 | `RiskGauge.jsx` |
| B6 | ✅ | State | Dashboard highestRisk 빈 상태 → "AI 평가 준비 중" | `Dashboard.jsx` |
| C1 | ✅ | Flow | PatientDetail 예측 → 환자 수정 시에만 재호출 | `PatientDetail.jsx` (sessionStorage 캐시) |
| C2 | ✅ | Flow | RiskAnalysis baseline 2.0/7.5 하드코딩 제거 | `RiskAnalysis.jsx` (null-safe + 가이드 화면) |
| C3 | ✅ | Flow | 검사수치 테이블 정상 범위 열 | `PatientDetail.jsx` (Info 툴팁) |
| C4 | ⬜ | Flow | CaseComparison before/after 같은 행 side-by-side | `CaseComparison.jsx` (현 디자인 유지 — 데모용) |
| C5 | ⬜ | Flow | EditPatientModal 섹션 아코디언 | `EditPatientModal.jsx` (long-form 유지 — 의사 편의) |
| D1 | ✅ | A11y | 컬러 대비 AA 미달 수정 | `Dashboard.jsx` (gauge heading 700, chart_no 500, gradient text /95), `PatientDetail.jsx` (gradient text /95) |
| D2 | ✅ | A11y | Modal focus trap + role=dialog + aria-modal | `EditPatientModal.jsx`, `ConfirmModal.jsx` |
| D3 | ✅ | A11y | CommandPalette role/aria | `CommandPalette.jsx` (combobox/listbox) |
| D4 | ✅ | A11y | Slider aria-valuetext | `RiskAnalysis.jsx` |
| D5 | ✅ | A11y | 이모지 aria-hidden | `RiskCard.jsx` |
| D6 | ✅ | A11y | 색각 배려 (아이콘 병기 ▲◆●) | `RiskBadge.jsx`, `RiskGauge.jsx`, `RadarChart.jsx` |
| D7 | ✅ | A11y | 드래그&드롭 키보드 경로 | `Home.jsx` (role=button + Enter/Space) |
| D8 | ✅ | A11y | aria-live 상태 변경 | `Home.jsx` (sr-only status + validation aria-live) |
| D9 | ✅ | A11y | 단축키 힌트 항상 표시 | `PatientList.jsx` (sm+ 화살표/검색, 모바일 / 만) |
| E1 | ✅ | Err | 예측 실패 재시도 버튼 | `PatientDetail.jsx`, `Dashboard.jsx` |
| E2 | ✅ | Err | 환자 0명 + /dashboard/:id 무한 스피너 | `Dashboard.jsx` (invalid patientId 가드 + 404/network 구분 + patientId 변경 시 stale state reset) |
| E3 | ✅ | Err | PatientList 페이지네이션 1~5 고정 버그 | `PatientList.jsx` (`paginationWindow` helper) |
| E4 | ⬜ | Err | Case 스텝 애니메이션 API 동기 | `CaseComparison.jsx` (디자인 유지) |
| E5 | ✅ | Err | window.confirm/alert → 커스텀 모달 | `Settings.jsx` (`useConfirm`) |
| F1 | ✅ | Resp | Sidebar 토글 (<xl) | `Sidebar.jsx`, `App.jsx` |
| F2 | ✅ | Resp | @media print (사이드바 숨김) + reduced-motion | `index.css` |
| G1 | ✅ | Copy | Dashboard 고정 고위험 문구 → level별 | `Dashboard.jsx` (`gaugeHeading`/`gaugeSubtitle`) |
| G2 | ✅ | Copy | "AI 분석 완료" → "AI 분석 N/M 모듈" | `PatientDetail.jsx` (동적) |
| G3 | ✅ | Copy | "로그인 불필요" 문구 제거 | `Sidebar.jsx` |
| G4 | ✅ | Copy | "12,000여 건" 허구 수치 제거 | `CaseComparison.jsx` (실 환자 수) |
| H1 | ✅ | Trust | 모델 메타데이터 UI (v/AUC/count) | `PatientDetail.jsx` + `theme.MODEL_META` |
| H2 | ✅ | Trust | 실제 환자 DB count API + UI | `usePatientCount` + `CaseComparison.jsx` |
| H3 | ✅ | Trust | CaseComparison ghost 카드 → 더미 배지 | `CaseComparison.jsx` (Info 배너) |
| I1 | ✅ | Perf | PatientContextBar 캐시 무효화 (수정 시) | `PatientContextBar.jsx` (`invalidatePatientContextCache`) + `PatientDetail.jsx` |
| I2 | ✅ | Perf | 슬라이더 요청 abort controller | `RiskAnalysis.jsx` |
| I3 | ✅ | Perf | Ghost 애니메이션 최소화 | `index.css` (prefers-reduced-motion) |
| J1 | ✅ | Sec | console.error PHI 제거/치환 | `prodSafeError` 적용: `PatientDetail`, `Dashboard`, `RiskAnalysis`, `CaseComparison`, `PatientList`, `Home` |
| J2 | ✅ | Sec | 환자명 마스킹 유틸 일관화 | `theme.maskName` |
| J3 | ✅ | Sec | CSV MIME/size 검증 | `Home.jsx` (`validateCsvFile`) |
| J4 | ✅ | Sec | 삭제/백업 2차 확인 | `Settings.jsx` (`useConfirm` + requireText='DELETE') |
| K1 | ✅ | Maint | Risk 레벨 enum 상수화 | `theme.RISK_LEVELS` |
| L1 | ✅ | ML | 인슐린/당뇨약 계수 상한 (역인과) v2.2-debias | `공통_전처리/train_debias_common.py` (Optuna 150×3 + Stacking + EE), `신장질환/retrain_v2_debias.py`, `심혈관/retrain_v2_debias.py`, `backend/ml/predictor.py` (Stacking 처리), `backend/ml/models/dkd_model.pkl`, `backend/ml/models/cvd_model.pkl` |
| M1 | ✅ | Nav | Sidebar Risk/Case 메뉴 disabled 안내 | `Sidebar.jsx` (Lock + aria-disabled) |
| M2 | ✅ | Nav | Patient List 메뉴 경로 /patients 고정 | `Sidebar.jsx` |
| N1 | ✅ | Etc | Header 시스템상태 실 헬스체크 | `Header.jsx` (axios.get(/health) 30s interval) |
| N2 | ✅ | Etc | audit trail (수정 이력 로그) | `models/database.py` (PatientAudit), `routers/patients.py` (PATCH diff + GET /audit), `components/PatientAuditCard.jsx`, `pages/PatientDetail.jsx` |

---

## NOTES

### 세션 3 (2026-04-25) 변경 파일
- **신규:**
  - `frontend/src/components/ConfirmModal.jsx` — 포커스 트랩 + role=dialog + requireText 2차 확인
  - `frontend/src/contexts/ConfirmContext.jsx` — Promise 기반 useConfirm hook
- **수정:**
  - `frontend/src/main.jsx` — `<ConfirmProvider>` 추가
  - `frontend/src/App.jsx` — 모바일 사이드바 대응 (left-0 → xl:left-64)
  - `frontend/src/index.css` — print 미디어, prefers-reduced-motion, .sr-only
  - `frontend/src/components/layout/Sidebar.jsx` — 모바일 토글 햄버거 + backdrop
  - `frontend/src/components/layout/Header.jsx` — 실 /health 폴링 + 햄버거 자리 패딩
  - `frontend/src/components/layout/PatientContextBar.jsx` — `invalidatePatientContextCache` + 이벤트 수신
  - `frontend/src/components/CommandPalette.jsx` — combobox/listbox/option ARIA
  - `frontend/src/components/EditPatientModal.jsx` — 포커스 트랩 + role=dialog + accent CSS var
  - `frontend/src/components/TrendChart.jsx` — Y 자동 도메인, 연도 포매터, ReferenceArea(정상범위), ReferenceLine(cut-off)
  - `frontend/src/pages/Settings.jsx` — `useConfirm` 도입 (reset/clearAllPatients)
  - `frontend/src/pages/Home.jsx` — CSV 검증, 드롭존 키보드, aria-live, accent 정리
  - `frontend/src/pages/PatientList.jsx` — `paginationWindow` 동적 윈도우, prodSafeError
  - `frontend/src/pages/PatientDetail.jsx` — `invalidatePatientContextCache` 호출

### 백업/버전
- v1.0.0 백업 위치: `C:\DangBom_project\_backup_v1.0.0\`
- 디자인 토큰은 `frontend/src/theme.js` 에 집중. 모든 레벨 색/문구 enum이 여기.

### 세션 4 (2026-04-25) 변경 파일
- **신규:**
  - `frontend/src/components/PatientAuditCard.jsx` — 환자 수정 이력 카드 (필드 한글 라벨 + timeAgo + 펼침/접기 + 새로고침).
- **수정 (백엔드):**
  - `backend/models/database.py` — `PatientAudit` ORM 추가 (patient_id FK CASCADE, changed_at, field_name, old/new_value, actor); `apply_lightweight_migrations()` 가 새 테이블도 보장.
  - `backend/routers/patients.py` — `_AUDIT_EXCLUDE` (자동파생/메타 제외), `_record_audit()` 헬퍼; PATCH 에서 변경 전후 diff 비교 후 기록 (실제 달라진 필드만); risk_level 변경은 `system:ml` actor 로 별도 기록; 신규 `GET /api/v1/patients/{id}/audit?limit=50` (최신순).
- **수정 (프론트):**
  - `frontend/src/pages/PatientDetail.jsx` — `PatientAuditCard` import + `auditRefreshKey` state, 수정 저장 후 `setAuditRefreshKey(k+1)` 트리거, 우측 CTA 스택에 카드 배치.
  - `frontend/src/pages/PatientList.jsx` — 단축키 힌트(D9): sm+ 에서 ←→ 페이지 + / 검색, 모바일은 / 만 노출 (공간 협소).

### 세션 5 (2026-04-25) 변경 파일
- **신규:**
  - `공통_전처리/train_debias_common.py` — Optuna 150 trials × {XGB, LGB, CB} + Stacking(LR meta) + EasyEnsemble + Youden vs Fbeta1.5 threshold 비교; 역인과 변수에 monotonic+1 / feature_weight=0.5 / sample_weight cap 0.7. KNNImputer + StandardScaler + 5-fold OOF.
  - `신장질환/retrain_v2_debias.py` — thin caller (n_trials=150, debias_cap=0.7).
  - `심혈관/retrain_v2_debias.py` — thin caller (n_trials=150, debias_cap=0.7).
- **수정:**
  - `backend/ml/predictor.py` — `_predict_proba_from_pkg()` 가 `model_type=="Stacking"` 일 때 base 3 모델 → meta LR 경로 처리.
  - `backend/ml/models/dkd_model.pkl` — v2.2-debias Stacking (XGB+LGB+CB → LR meta), val AUC 0.7524, sens 0.630, spec 0.694, threshold 0.4368.
  - `backend/ml/models/cvd_model.pkl` — v2.2-debias EasyEnsemble n=50, val AUC 0.7608, sens 0.667, spec 0.703, threshold 0.5463.

### v2.2-debias 비교 결과 (선정 기준: OOF AUC)
**DKD (3988 dev / 997 val, prev 2.7%)**

| 모델 | OOF AUC | Val AUC | Sens | Spec | F1 |
|-----|---------|---------|------|------|----|
| XGBoost | 0.7316 | 0.7670 | 0.519 | 0.788 | 0.113 |
| LightGBM | 0.7730 | 0.7452 | 0.704 | 0.645 | 0.097 |
| CatBoost | 0.7853 | 0.7517 | 0.630 | 0.694 | 0.100 |
| **Stacking ✅** | **0.7854** | **0.7524** | **0.630** | **0.694** | **0.100** |
| EasyEnsemble | 0.7565 | 0.7401 | 0.556 | 0.730 | 0.099 |

**CVD (2788 dev / 697 val, prev 12.4%)**

| 모델 | OOF AUC | Val AUC | Sens | Spec | F1 |
|-----|---------|---------|------|------|----|
| XGBoost | 0.6633 | 0.6990 | 0.897 | 0.407 | 0.247 |
| LightGBM | 0.6388 | 0.6550 | 0.770 | 0.480 | 0.225 |
| CatBoost | 0.6549 | 0.6956 | 0.908 | 0.392 | 0.246 |
| Stacking | 0.6637 | 0.7071 | 0.931 | 0.370 | 0.247 |
| **EasyEnsemble (n=50) ✅** | **0.6952** | **0.7608** | **0.667** | **0.703** | **0.301** |

### 후속 작업 (다음 세션)
1. **C4, C5, E4** — 디자이너 결정 사항으로 현재 디자인 유지. 추가 작업 불요.
2. **모든 핵심 TODO 처리 완료** — cron 자체 정리 가능 (CronList → CronDelete 후 종료).

### 세션 6 (2026-04-26) 변경 파일
- **수정:**
  - `frontend/src/pages/Dashboard.jsx` — E2: validPatientId 가드 + errorKind 분기(`not_found`/`network`/`unknown`) + patientId 변경 useEffect 로 stale state reset; D1: gaugeHeadingColor 700 (AA 4.5:1), chart_no text-gray-500, gradient CTA text-white/95.
  - `frontend/src/pages/PatientDetail.jsx` — D1: 우측 CTA gradient 본문 text-white/85 → /95.
  - `frontend/src/theme.js` — MODEL_META 동기화: kidney algorithm 'EasyEnsemble' → 'Stacking', AUC 0.759 → 0.752; cardio AUC 0.755 → 0.761; 둘 다 version 'v2.2-debias'.
  - `CHECKPOINT.md` — STATUS/TODO/NOTES 갱신 (E2/D1 ✅).

### v2.2-debias 역인과 완화 가중치 요약
세 변수 (insulin_medication, DM_medication) 에 적용:

| 처리 | 값 | 적용 알고리즘 | 효과 |
|------|----|---|---|
| ① monotone_constraint | +1 | XGB / LGB / CatBoost | "투약↑→위험↑" 자연 방향만 학습 (역방향 차단) |
| ② feature_weight | 0.5 | XGB only (LGB/CB 미지원) | tree split 후보로 선택될 확률 절반 |
| ③ sample_weight cap | 0.7 | 모든 알고리즘 (EasyEnsemble 포함) | 두 변수 중 하나라도 ≥1 인 샘플 학습 가중치 30% 감소 |

CVD 최종 모델 (EasyEnsemble) 은 ③만 적용 (AdaBoost.SAMME 가 monotone/feature_weight 미지원). DKD Stacking 은 base XGB/LGB/CB 모두에 ①+③ 적용 (XGB 만 추가로 ②).

