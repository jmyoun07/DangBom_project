#!/usr/bin/env bash
# ======================================
#  DB-care 의존성 설치 스크립트 (Mac/Linux)
#  최초 1회만 실행하면 됩니다.
# ======================================
set -e

cd "$(dirname "$0")"

echo
echo "============================================"
echo " DB-care 설치 프로그램"
echo "============================================"
echo

# Python 확인
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 이 설치되어 있지 않습니다."
    echo "Mac: brew install python@3.11"
    echo "Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python 버전: $PYTHON_VERSION"

echo "[1/3] 가상환경 생성 중..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "[2/3] 가상환경 활성화..."
# shellcheck source=/dev/null
source venv/bin/activate

echo "[3/3] 의존성 패키지 설치 중... (약 2~3분)"
pip install --upgrade pip
pip install -r backend/requirements.txt

echo
echo "============================================"
echo " 설치 완료!"
echo
echo " 이제 'bash start.sh' 로 프로그램을 실행할 수 있습니다."
echo "============================================"
