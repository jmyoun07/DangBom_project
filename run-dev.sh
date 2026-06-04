#!/usr/bin/env bash
# DB-care 개발 서버 실행 — 백엔드(FastAPI :8000) + 프론트(Vite :5173)
# 사용:  ./run-dev.sh        (Ctrl+C 로 둘 다 종료)
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# 기존 8000 점유 프로세스 정리 (이전 인스턴스 충돌 방지)
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true

# 1) 백엔드 (백그라운드, --reload = 코드 저장 시 자동 재시작)
cd "$ROOT/backend"
.venv/bin/python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 &
BACK_PID=$!
echo "▶ 백엔드  http://127.0.0.1:8000  (PID $BACK_PID)"

# 프론트 종료(Ctrl+C) 시 백엔드도 함께 종료
trap "echo; echo '서버 종료 중...'; kill $BACK_PID 2>/dev/null || true" EXIT

# 2) 프론트 (포그라운드) — http://localhost:5173
cd "$ROOT/frontend"
echo "▶ 프론트  http://localhost:5173"
echo "----------------------------------------"
npm run dev
