# DB-care 하네스 엔지니어링 실행 가이드 v2

## 폴더 구조 (완성 후 기준)
```
db-care/                          ← 이 폴더를 Claude Code에 권한 부여
├── CLAUDE.md                     ← 마스터 지침 (Claude가 항상 먼저 읽음)
├── harness/
│   ├── orchestrator.py           ← 자동 실행 스크립트
│   ├── sprint_status.md          ← 진행 상태 (자동 업데이트)
│   ├── sprint_01_contract.md     ← 백엔드 + ML 예측 API
│   ├── sprint_02_contract.md     ← 프론트엔드 + Dashboard
│   ├── sprint_03_contract.md     ← RiskAnalysis 시나리오
│   ├── sprint_04_contract.md     ← PatientList + PatientDetail
│   ├── sprint_05_contract.md     ← Home CSV + CaseComparison
│   └── sprint_06_contract.md     ← 통합 테스트 + 폴리싱
├── backend/
│   └── ml/
│       └── models/               ← .pkl 파일 여기에 넣기
│           ├── dkd_model.pkl
│           ├── retinopathy_model.pkl
│           └── neuropathy_model.pkl
└── frontend/                     ← Generator가 자동 생성
```

---

## 사전 준비

```bash
# 1. Claude Code 설치 확인
claude --version
# 없으면: npm install -g @anthropic-ai/claude-code

# 2. Python 환경 (3.11+)
python --version

# 3. Node.js (18+)
node --version

# 4. 환경변수 설정
export ANTHROPIC_API_KEY="sk-ant-..."

# 5. 하네스 의존성
pip install anthropic
```

---

## 실행 방법

### 방법 A: 완전 자동 실행 (권장)
```bash
cd db-care폴더
python harness/orchestrator.py        # Sprint 1~6 전체
python harness/orchestrator.py 1 3   # Sprint 1~3만
python harness/orchestrator.py 3 3   # Sprint 3만 재실행
```

### 방법 B: Claude Code 직접 실행 (수동)
```bash
cd db-care폴더
claude   # Claude Code 실행
```
Claude Code 채팅창에 입력:
```
CLAUDE.md와 harness/sprint_01_contract.md를 읽고 Sprint 1을 구현해줘.
완료 후 harness/sprint_01_result.md를 작성하고 sprint_status.md를 업데이트해줘.
```

---

## 모니터링

```bash
# 현재 진행 상태
cat harness/sprint_status.md

# 특정 스프린트 평가 결과
cat harness/sprint_01_eval.json

# 백엔드 실행 (테스트)
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 프론트엔드 실행 (테스트)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

---

## 문제 해결

| 문제 | 해결 |
|------|------|
| `claude` 명령어 없음 | `npm install -g @anthropic-ai/claude-code` |
| pkl 파일 없음 | 자동으로 더미 예측값 fallback 사용 |
| 스프린트 계속 실패 | `sprint_XX_eval.json` 확인 후 계약 파일 보완 |
| API 연결 안됨 | `export ANTHROPIC_API_KEY=...` 확인 |

---

## 스프린트별 예상 비용 및 시간

| 스프린트 | 내용 | 예상 시간 | 예상 비용 |
|----------|------|-----------|-----------|
| Sprint 1 | 백엔드 + ML API | 30~60분 | $10~20 |
| Sprint 2 | 프론트 기반 + Dashboard | 60~90분 | $20~35 |
| Sprint 3 | RiskAnalysis 시나리오 ★ | 60~90분 | $20~35 |
| Sprint 4 | PatientList + Detail | 45~60분 | $15~25 |
| Sprint 5 | Home + CaseComparison | 45~60분 | $15~25 |
| Sprint 6 | 통합 테스트 + 폴리싱 | 30~45분 | $10~15 |
| **합계** | | **5~7시간** | **$90~155** |

재시도 발생 시 추가 비용 발생 (스프린트당 최대 3회)
