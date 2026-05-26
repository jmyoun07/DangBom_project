# Sprint 6 결과 — 통합 테스트 + 버그 수정 + UI 폴리싱

**완료일**: 2026-04-16
**상태**: ✅ 12/12 검증 기준 PASS

---

## 실행 요약

Sprint 2~5에서 구현된 6개 프론트엔드 페이지(Home, Dashboard, PatientList,
PatientDetail, RiskAnalysis, CaseComparison)에 대해 브라우저 E2E 검증을
수행하고 렌더링 버그를 수정했다.

백엔드(FastAPI :8000) + 프론트엔드(Vite :5173) 동시 기동 상태에서 모든
페이지가 정상 렌더되고 실제 API 응답이 UI에 반영됨을 확인했다.

---

## 발견 및 수정한 버그

### JSX 유니코드 이스케이프 렌더링 버그 (총 10개 수정)

JSX 텍스트·속성에서 `\u2022`, `\u2192`, `\u26A0`, `\uC800\uC704\uD5D8` 등
유니코드 이스케이프 시퀀스를 문자열 리터럴(`{'...'}`) 바깥에 직접 배치하면
리터럴 문자열 `\u2192` 그대로 화면에 출력되는 버그.

| # | 파일 | 라인 | 증상 |
|---|------|------|------|
| 1 | pages/RiskAnalysis.jsx | 204 | `1개 \u2192 4개` 텍스트 그대로 표시 |
| 2 | pages/RiskAnalysis.jsx | 254 | HbA1c before→after 화살표 미표시 |
| 3 | pages/RiskAnalysis.jsx | 258 | C-peptide before→after 화살표 미표시 |
| 4 | pages/RiskAnalysis.jsx | 222 | 전조 증상 bullet 점 미표시 (이전 수정) |
| 5 | pages/RiskAnalysis.jsx | 272 | 기대 변화 bullet 점 미표시 (이전 수정) |
| 6 | pages/CaseComparison.jsx | 42 | HbA1c before→after 화살표 미표시 |
| 7 | pages/Home.jsx | 227 | 에러 목록 ⚠ 아이콘 미표시 |
| 8 | pages/Home.jsx | 242 | 경고 목록 ⚠ 아이콘 미표시 |
| 9 | pages/Dashboard.jsx | 189 | C-peptide 추이 차트 제목 `\uC218\uCE58 \uCD94\uC774` 그대로 표시 (JSX prop 더블쿼트 안 escape 미처리) |
| 10 | pages/PatientList.jsx | 67-69 | 위험도 필터 option value가 `\uC800\uC704\uD5D8`로 전송 → 필터 동작 불능 |

**수정 패턴**:
- JSX 텍스트 내: `\u2192` → `{'\u2192'}`
- JSX 속성 내: `title="... \uXXXX"` → `title={'... \uXXXX'}`

### 루트 원인

JSX의 attribute double-quote는 HTML처럼 literal로 처리되어 JS escape가
해석되지 않음. JSX 텍스트 컨텐츠도 동일. 반드시 중괄호 내 문자열 리터럴로
감싸야 JS 파서가 `\u2192`를 유니코드 코드포인트 0x2192(→)로 변환함.

---

## 검증 결과 (12개 기준)

### 기능 완성도 (8/8 PASS)

| # | 항목 | 결과 | 증거 |
|---|------|------|------|
| 1 | 전체 6개 페이지 접근 가능 | ✅ PASS | /home, /dashboard/:id, /patients, /patients/:id, /risk-analysis/:id, /case-comparison/:id 전부 200 렌더 |
| 2 | 사이드바 모든 메뉴 정상 이동 | ✅ PASS | Sidebar.jsx NavLink 5개 + Logout 항목 정상 동작 |
| 3 | Dashboard 데이터 실제 API 연동 | ✅ PASS | /patients/1 + /predict 병렬 호출로 HbA1c 9.3%, SBP 137, BMI 33 등 실제 값 반영 |
| 4 | RiskAnalysis 슬라이더 실시간 동작 | ✅ PASS | C-peptide(0.5~5.0), HbA1c(5.0~15.0) debounce 300ms 후 /scenario/simulate 호출 |
| 5 | 시나리오 방치/집중관리 수치 다름 | ✅ PASS | 방치 65세/1391만, 집중관리 81세/365만 — 16세 / 1026만원 차이 |
| 6 | CaseComparison 3개 카드 표시 | ✅ PASS | 김*현 86%, 이*수 81%, 박*진 80% 3개 케이스 카드 렌더 |
| 7 | CSV 업로드 후 환자 목록 반영 | ✅ PASS | POST /upload/csv 후 /patients 목록 즉시 갱신 (Sprint 5 검증 완료) |
| 8 | 환자 상세 추이 차트 3개 | ✅ PASS | C-peptide, HbA1c, Cr 크레아티닌 TrendChart 3개 모두 렌더 |

### UI 품질 (4/4 PASS)

| # | 항목 | 결과 | 증거 |
|---|------|------|------|
| 9 | 위험도 색상 규칙 일관성 | ✅ PASS | RiskBadge/RiskBar/RiskGauge 공통 컴포넌트 사용 — 고위험=red, 중위험=yellow/orange, 저위험=green 전 페이지 일관 |
| 10 | 로딩 상태 표시 | ✅ PASS | 모든 페이지 초기 fetch 중 animate-spin 로더 표시 |
| 11 | 에러 상태 표시 | ✅ PASS | Home 업로드 에러 목록 패널, API 실패 시 try/catch → feedback.errors 배열에 detail 표시 |
| 12 | 1280px 레이아웃 정상 | ✅ PASS | preview_resize desktop(1280x800) 프리셋에서 사이드바 w-64 + 메인 3열/6-column grid 유지 |

---

## 브라우저 E2E 확인 로그 (Claude Preview)

```
GET /home         → "CSV 파일을 드래그하거나 클릭하여 업로드", 템플릿 다운로드 버튼 표시
GET /dashboard/1  → HbA1c 9.3%, 혈압 137/74.7, 기간 12년
                    6개 카드 중 신장/심혈관/망막 3개 위험도 표시, 치매/신경병/뇌혈관 "준비 중"
                    C-peptide 추이 차트 렌더 (수정 후 "수치 추이" 한글 정상 표시)
GET /patients     → 전체 10명, 8명/페이지 페이징, 위험도 필터=고위험 → 3명 (이승철/최동우/한지영)
GET /patients/1   → 14개 검사 수치 좌 7 / 우 7 분할, 3개 추이 차트, 3개 AI 예측 카드
GET /risk-analysis/1
                  → C-peptide 1.7 ng/mL, HbA1c 9.3% 슬라이더
                    방치: 65세 / 1,391만원 / 4개 bullet 전조증상 (점 정상)
                    집중: 81세 / 365만원 / 4개 bullet 변화 (점 정상)
                    지표 예측: "7.5% → 6.3%" 화살표 정상
GET /case-comparison/1
                  → 4단계 스텝퍼 완료, 3개 매칭카드(86%/81%/80%)
                    HbA1c 변화 "8.7% → 7%" 화살표 정상
```

---

## 산출물

- `frontend/src/pages/Home.jsx` — ⚠ 아이콘 2건 수정
- `frontend/src/pages/Dashboard.jsx` — TrendChart title prop 수정
- `frontend/src/pages/PatientList.jsx` — 위험도 필터 option value 3건 수정
- `frontend/src/pages/RiskAnalysis.jsx` — → 화살표 3건 수정
- `frontend/src/pages/CaseComparison.jsx` — → 화살표 1건 수정
- `.claude/launch.json` — Claude Preview dev 서버 설정 신규 생성

---

## 종료 상태

- 백엔드 :8000 실행 중 (FastAPI)
- 프론트엔드 :5173 실행 중 (Vite)
- 모든 페이지 브라우저에서 정상 렌더 확인
- 병원 데모 준비 완료
