#!/usr/bin/env bash
# ======================================
#  DB-care 실행 스크립트 (Mac/Linux)
# ======================================
set -e

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "[ERROR] 아직 설치가 완료되지 않았습니다."
    echo "먼저 'bash install.sh' 를 실행해주세요."
    exit 1
fi

# shellcheck source=/dev/null
source venv/bin/activate

echo
echo "============================================"
echo " DB-care 서버 시작 중..."
echo " 브라우저가 잠시 후 자동으로 열립니다."
echo " 종료하려면 Ctrl+C 를 누르세요."
echo "============================================"
echo

# 백그라운드 브라우저 실행
(
    sleep 3
    if command -v open &> /dev/null; then
        open "http://localhost:8000"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "http://localhost:8000"
    fi
) &

cd backend
export DBCARE_MODE=production
python -m uvicorn main:app --host 0.0.0.0 --port 8000
