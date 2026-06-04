# 새벽 QA 로그 — DB-care v2.2.1 → v2.2.2 (2026-06-04 야간)

> 목표: **의료진이 봤을 때 "의아함(이상하다)"이 안 들도록** 전면 점검.
> 방식: Claude(수치/기능/UI 스윕) ↔ codex(임상 로직 독립 감사) 역할분담 → 교차검증 → 수정 → 재검토.
> 통과 시에만 GitHub(Yamsamg/DangBom_project) push (→ Windows 빌드/Release CI).

## 엄격 통과 기준 (PUSH GATE) — 전부 충족해야 push
1. 병원 피드백 F1~F5 전부 해결 또는 의식적 안전-보류(사유 기록).
2. 의료진이 의문 가질 의료 로직 0건 (위험도 ↔ 수치 정합, 또는 사유 명시).
3. 교차 페이지 일관성: 동일 환자 위험등급이 Dashboard / PatientDetail / RiskAnalysis 전부 일치.
4. 수치 이상 0건: NaN/음수/비현실값/널렌더 없음 (전 환자 × 전 엔드포인트).
5. 백엔드 기능 스윕 invariant 전부 green (전 환자).
6. 프론트 `vite build` 성공 + 주요 페이지 콘솔 에러 0.
7. 슬라이더 시뮬레이션 단조·자연스러움 (점프/역전 없음).
8. codex 독립 감사 High/Critical 미해결 0건.
9. 버전 2.2.2 bump (frontend package.json + tauri.conf.json).
10. 정상 환자 회귀 0건.

## 도구
- 자동 스윕: `harness/qa_sweep.py` (venv python으로 실행) — 의아함 자동 탐지.
- codex: agent-link `spawn_agent` (임상 감사 역할).

---

## 라운드 로그
(각 라운드마다 발견 → 수정 → 검증 결과 누적)

### Round 1 (발견) — 2026-06-04 야간
**자동 스윕(qa_sweep.py, 20명)**: CRIT 0 / HIGH 0 → 백엔드 수치 GATE PASS.
- MED 7: `F5_lowAUC_only` — 신규3개 저AUC 모델이 정상지표 환자를 중위험 (박순분 A1c6.7→치매·뇌혈관, 이준해 A1c6.7→뇌혈관 등). = F5(b).
- LOW 40: `F5_reason_hidden` — floor/flag 로 상향됐는데 카드에 사유 숨김.

**codex 임상감사 (codex-5419ff)** High 5 / Med 7 / Low 1:
- H1. floor 고위험 승격인데 score/bar 는 raw → "고위험인데 1/100" (Dashboard.jsx:312, RiskGauge.jsx:15, PatientDetail.jsx:363, RiskBar.jsx:27)
- H2. PATCH 후 파생값(eGFR/LDL/HOMA/TyG/BMI) 재계산 안 됨 (patients.py:477)
- H3. predict/scenario 는 저장 age/dm_duration, PatientDetail 은 현재 나이 → 페이지간 불일치 (scenario.py:289, prediction.py:14, patients.py:80)
- H4. 저AUC 선별모델 경고 제거 + 6/6 완성처럼 표시 (predictor.py:121/970, theme.js:126)
- H5. 집중관리 안전망 미적용 → HbA1c≥11 이후도 저/중위험 (scenario.py:435/444)
- M6. 핵심검사 결측 시 정상기본값으로 채워 available 처리 (predictor.py:282, upload.py:378)
- M7. 정상범위 기준 페이지/모듈마다 상이 (Dashboard.jsx:40, PatientDetail.jsx:24, theme.js:237, CLAUDE.md)
- M8. 음수 LDL/맥압 가능 (schemas.py:40, derived.py:141/184)
- M9. Dashboard eGFR 프론트 별도계산 → 백엔드와 상이 (Dashboard.jsx:80)
- M10. 유사사례 6개 중 3개만, level/flag 없음 (case_comparison.py:205)
- M11. 유사사례 개선이력 없어도 의료비절감/수명증가 표시 (case_comparison.py:319/331)
- M12. patients risk_level fallback 이 predictor 안전망과 모순 (patients.py:117)
- L13. "C-peptide 1% 개선" 단위/방향 오해소지 (RiskAnalysis.jsx:429)
- 검증필요: eGFR CKD-EPI 2009 vs 2021, HOMA-IR 1.69 스케일, C-peptide 정상범위 하한 확정.

**수정 계획(우선순위)**: H5(집중관리 floor) → H1+LOW40(display_score+사유노출) → H3(나이) → H2(PATCH 파생) → M8(음수가드) → H4/M6(저AUC 경고) → M7(정상범위 통합) → M10~12(유사사례). 각 수정 후 sweep+codex 재검증.

### Round 2 (백엔드 수정 + codex 적대적 검증) — 2026-06-04 야간
**Claude 백엔드 수정 (1차)**: H1(display_score) · H5(집중관리 floor 재적용) · H3(현재나이) · H2(PATCH 파생) · H4(model_role) · M8(음수가드).
**codex 라운드2 (codex-5808d4)** 가 내 1차 수정의 실제 버그 적발:
- H2 ❌: EditPatientModal 이 파생필드(age/bmi/he_insulin)를 항상 PATCH → `if f not in changes` 가 재계산을 영영 skip. + None 일 때 stale clear 안 함.
- H3 ❌: patient_to_features 만 현재나이, apply_clinical_floor/percentile 은 원본 stale → predict_all 내부 불일치. + patient_to_features 내부 `age-dm_diagnosis_age` 음수 가능.
- H1 ⚠️: 프론트가 아직 score 사용 → 바 모순 잔존 (프론트 미완).
- H5 ⚠️: floor dict 가 stale age/dur 사용 + 졸업이 floor 무시(eGFR<45 과소표시).
- M8 ⚠️: patient_to_features(모델입력)는 여전히 음수 생성.
- H4 ⚠️: 프론트 model_role 미사용.
- 신규: Rule5 UACR 필드 schema 부재 → 발동 불가(무해).

**Claude 2차 수정 (codex 반영)**: predict_all `_normalize_age_duration` 1회 정규화(features+floor+percentile 일관) / patient_to_features 음수 LDL·non_HDL·맥압·dm_dur 가드 / `_recompute_derived` 항상 재계산(PURE clear-on-None, SOFT 보존) / 집중관리 floor 에 현재 age·dm_duration 주입 / 졸업도 잔존 안전망(_max_level) 존중.
**검증**: codex 재현 케이스 전부 수정 확인(H2 bmi/he_insulin 갱신·H3 dm_dur 16·미래dob nan·M8 nan) + 전체 스윕 CRIT/HIGH 0 유지.
**남은 것**: 프론트 배치(H1 display_score 사용·F5 사유노출·H4 선별배지·M7 정상범위·M9 eGFR·L13 문구) → build+preview → codex R3 → 버전 bump → push.

### Round 3 (프론트 배치 + preview 검증) — 2026-06-04 야간
**구현**: RadarChart/Dashboard/PatientDetail 가 `display_score ?? score` 사용(H1) / RiskCard·PatientDetail 에 임상 사유 항상 노출(F5, 로딩 타이밍 무관하게 toggle 분리) / `model_role==='screening'` 선별 배지+문구(H4).
**preview 검증 (vite dev + 새 backend :8000)**:
- H1 ✅ 권선호 대시보드 6카드 진행바 60/100(고위험 밴드, 이전 raw 1~29) · PatientDetail 위험지수 전부 60 · RiskAnalysis 라다 데이터폴리곤 spread 105px(=값60).
- F5 ✅ 6카드 모두 "HbA1c 13.9% — 무조건 고위험 안전망 적용 (ADA 2026)" 사유 클릭없이 표시.
- H4 ✅ 치매·신경병증·뇌혈관 "선별" 배지 + "선별용 모델 — 임상 확인 필요". 정상환자 박순분(A1c6.7)도 선별모델 중위험에 배지 표시(고위험 0).
- H3 ✅ 나이 61세(현재) 표시. H5 ✅ 시나리오 방치/집중 고위험, 졸업 저위험.
- 콘솔 에러 0 (대시보드 7·2, 상세 7, 시나리오 7). vite build 성공.
**미결(검토중)**: M7(정상범위 페이지간 불일치)·M9(Dashboard eGFR)·M10/11(유사사례)·L13(문구) → codex R3 가 push-blocking 여부 판정.
**열린 UX 질문**: H5 로 집중관리(6개월)도 hba1c_after≥11 환자는 고위험 표시 — 의학적으로 정직하나 "관리해도 고위험" 메시지. codex R3 의견 + 사용자 결정 대상.

### Round 4 (블로커 수정) + PUSH — 2026-06-04 야간
**codex R3 = NO-GO** (블로커 1): scenario.radar 숫자반환 → 프론트 30/60 fallback 재분류로 모델 threshold 중위험을 저위험 과소표시.
**수정**: radar_display 를 `{score, display_score, level}` 객체로 반환 → RadarChart 가 backend level 사용. 검증: 박순분 dementia 19.6 → 라다 amber(중위험), 콘솔 0.
**codex R4 = GO** (codex-e819ff): 블로커 해소·회귀 없음 확인.
**추가**: L13 문구 정정(C-peptide 1%→HbA1c 1%↓), 버전 2.2.2 bump(package.json·tauri.conf.json·main.py×2).

## 엄격 GATE 결과 (전부 충족 ✅)
1 F1~F5 ✅(F4 라벨 후속·기록) / 2 의료로직 ✅(codex GO) / 3 교차일관성 ✅ / 4 수치이상 0 ✅ / 5 sweep green ✅ / 6 build+console 0 ✅ / 7 단조성 ✅ / 8 codex High/Crit 0 ✅ / 9 2.2.2 ✅ / 10 회귀 0 ✅.

## PUSH 완료
- commit **a34f2d6** → origin/main (15파일 +690/-38)
- CI run **26901426657** in_progress (Windows 빌드) — green 확인 후 tag v2.2.2 로 Release.

### Round 5 (사용자 추가 요청) — 졸업 박스 고정
- a34f2d6 CI run 26901426657 = **success** (Windows 빌드·6모델 스모크 통과) 확인. (release 태그 전 poller 외부 중지됨)
- **요청**: 졸업 박스의 예상 건강수명·의료비가 슬라이더(시뮬레이션)에 따라 움직이면 안 됨.
- **원인**: F1 수정 때 grad_life=max(.., intensive_life+2)/grad_cost=min(.., cost_after-5) 로 슬라이더 의존 도입.
- **수정**: scenario.py — grad_life=max(62, age+5, int(82−age/10+10)) / grad_cost=clamp(40+age*0.2,40,55).
  age 만 의존(고정). F1 단조성은 고정 졸업값이 슬라이더 전 구간 집중값을 항상 능가/하회하도록 범위 설계로 보장(clamp 불필요).
- **검증**: 권선호 슬라이더 4위치(cp0.5~3, a1c6~13.9) 졸업 life=85/cost=52 불변, 집중·방치는 변동. 전 환자 단조성 0위반.
  UI 시연: HbA1c 13.9→6.0 시 졸업 박스 불변(85세/52만), 집중관리 77→83세 변동. sweep CRIT/HIGH 0.

### Round 6 (사용자 추가 요청) — 집중관리 → 졸업 수렴
- **질문**: 슬라이더를 졸업값(5.6/1.3)에 맞추면 집중관리도 졸업(85/52)에 도달해야 하지 않나? (사용자 선택: "졸업값에 수렴")
- **원인 설명**: 졸업은 6개 값 정규화(+sbp120/dbp80/bmi22/fbg90), 슬라이더는 2개만. 집중 수명/의료비는 ML 잔여위험(baseline_sev) 휴리스틱. + 졸업 고정 anchor 설계.
- **수정**: scenario.py — `managed_gap`(혈당 슬라이더 + 비정상 동반수치 이탈도) → `grad_conv`(0~1) 로 집중관리 수명·의료비를 졸업 anchor 로 보간. gap0 → 집중=졸업. 보간 범위가 [휴리스틱, 졸업]이라 단조성 자동 보존. GRADUATION_VALUES/grad_life/grad_cost 단일 정의로 통합.
- **검증**: 환자7(동반수치 정상)=완전수렴 85/52=85/52, 환자2(sbp138/bmi18)=소폭격차(84/63 vs 84/55), 환자8(bmi34)=격차유지. 전 환자×3슬라이더 단조성 0위반. UI 시연 + sweep CRIT/HIGH 0.

### Round 7 (사용자 추가 요청) — 게이지 행 통일 + 로직 문서
- **게이지 행 높이 통일**: 방치/집중/졸업 카드 합병증 행이 부가텍스트("같은 나이대 대비", "방치 대비 감소") 유무로 높이가 달랐음 → 각 행 `min-h-[40px]` 래퍼로 통일. 18개 행(3카드×6) 전부 40px 측정 확인, 열 정렬됨.
- **로직 문서**: `docs/위험도_계산_로직.md` 신규 — ML/안전망/수치기반 3출처 구분, 페이지별 요소별 출처+공식, "이 숫자 어디서 나왔나" 색인, 의료진 FAQ. 위험요인 패널이 수치기반(ML 아님)임 명시 등.

## 후속(non-blocking, 사용자 결정)
- F4 위험요인 패널 top_drivers / M7 정상범위 단일모듈 통합 / M9 Dashboard eGFR backend소스 / M10·11 유사사례 더미 절감액 정직화 / H5 집중관리 hba1c 강하폭(-1.0) 재검토.

