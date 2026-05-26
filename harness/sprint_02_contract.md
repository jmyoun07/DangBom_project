# Sprint 2 계약: 프론트엔드 기반 + 공통 컴포넌트 + Dashboard

## 목표
React + Vite + TailwindCSS 앱 초기화.
공통 컴포넌트(RiskGauge, RiskCard, RiskBadge, RiskBar, TrendChart) 구현.
Dashboard 페이지를 Visily UI와 동일하게 구현.

---

## 구현 항목

### 1. 프론트엔드 초기화
- [ ] Vite + React 프로젝트 생성
- [ ] TailwindCSS 설치 및 설정
- [ ] Recharts 설치
- [ ] react-router-dom 설치 + 라우팅 설정 (6개 페이지)
- [ ] Axios 클라이언트 (baseURL: http://localhost:8000/api/v1)

### 2. 공통 레이아웃 (Sidebar + Header)
Sidebar:
- 배경: #1e1e2e (다크 네이비)
- 상단: DB-care 로고 (흰색)
- 메뉴 6개: Home / Dashboard / Patient List / Risk Analysis / Case Comparison / Settings
- 하단: Logout
- 활성 메뉴: 보라색 배경 + 흰색 텍스트

Header:
- DB-care 로고 + 페이지명
- 검색 아이콘 + 알림 아이콘
- 사용자 정보 (이름 + 소속 + 아바타)

### 3. 공통 컴포넌트

**RiskGauge.jsx** — SVG 반원 게이지
```
props: score(0~100), level("저위험"|"중위험"|"고위험")
- 반원 arc: 저위험=초록, 중위험=주황, 고위험=빨강
- 중앙 텍스트: 레벨명 (굵게, 색상 일치)
- 하단 텍스트: "RISK GAUGE"
```

**RiskBadge.jsx** — 위험도 배지
```
props: level("저위험"|"중위험"|"고위험")
- 고위험: bg-red-100 text-red-600 border border-red-200
- 중위험: bg-yellow-100 text-yellow-600 border border-yellow-200
- 저위험: bg-green-100 text-green-600 border border-green-200
```

**RiskBar.jsx** — 컬러 진행 바
```
props: score(0~100), level
- 0~33%: 초록, 34~66%: 주황, 67~100%: 빨강
- 높이: h-1.5, 둥근 모서리
```

**RiskCard.jsx** — 합병증별 카드
```
props: name, englishName, icon, level, metricLabel, metricValue, available
- available=false: 위험도 배지 없이 "분석 준비 중" 표시
```

**TrendChart.jsx** — 수치 추이 LineChart
```
props: data([{month, value}]), unit, color
- Recharts LineChart, 부드러운 곡선 (type="monotone")
- 원형 포인트 (dot)
```

### 4. Dashboard 페이지 (CLAUDE.md PAGE 2 스펙 구현)
- [ ] 3열 레이아웃 구현
- [ ] 환자 정보 카드 (API: GET /api/v1/patients/{id})
- [ ] CRITICAL STATUS 게이지 (RiskGauge 사용)
- [ ] C-peptide 추이 차트 (TrendChart 사용)
- [ ] 합병증 카드 6개 그리드 (RiskCard 사용, 미완성 3개 "분석 준비 중")
- [ ] 주요 위험 요인 분석 패널
- [ ] Risk Analysis 바로가기 CTA

---

## 검증 기준

| # | 기준 | 방법 |
|---|------|------|
| 1 | React 앱 localhost:5173 정상 실행 | 브라우저 접속 |
| 2 | 사이드바 메뉴 6개 표시 + 네비게이션 | 클릭 이동 |
| 3 | Dashboard 합병증 카드 6개 렌더링 | 화면 확인 |
| 4 | RiskGauge 고위험=빨강, 저위험=초록 | 스코어 변경 확인 |
| 5 | 미완성 3개 알고리즘 "분석 준비 중" 표시 | 화면 확인 |
| 6 | 백엔드 API 연동 (실제 환자 데이터 표시) | 네트워크 탭 |
| 7 | C-peptide 추이 차트 렌더링 | Recharts 표시 |

## 완료 정의
7개 기준 모두 PASS
