#!/usr/bin/env bash
# ==================================================
#  DB-care Release Builder (Mac/Linux)
# ==================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALLER="$ROOT/installer"
FRONTEND="$ROOT/frontend"
BACKEND="$ROOT/backend"
TEMPLATE="$INSTALLER/template"
DIST_ROOT="$ROOT/dist"
BUILD_ROOT="$INSTALLER/build"
STAGE="$BUILD_ROOT/DB-care"

VERSION="1.0.0"
ZIP_NAME="DB-care-v${VERSION}.zip"
ZIP_PATH="$DIST_ROOT/$ZIP_NAME"

echo ""
echo "======================================"
echo " DB-care Release Builder v${VERSION}"
echo "======================================"
echo ""

echo "[1/5] 이전 빌드 정리..."
rm -rf "$BUILD_ROOT"
mkdir -p "$STAGE"
mkdir -p "$DIST_ROOT"

echo "[2/5] 프론트엔드 빌드..."
cd "$FRONTEND"
if [ ! -d "node_modules" ]; then
    echo "    node_modules 없음 → npm install"
    npm install
fi
npm run build
cd "$ROOT"

echo "[3/5] 패키징 (백엔드 + 빌드된 프론트엔드)..."

rsync -a \
    --exclude='__pycache__' \
    --exclude='venv' --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='*.pyc' --exclude='*.db' \
    "$BACKEND/" "$STAGE/backend/"

cp -R "$FRONTEND/dist" "$STAGE/frontend_dist"

echo "[4/5] 실행 스크립트 복사..."
cp "$TEMPLATE"/* "$STAGE/"
chmod +x "$STAGE/install.sh" "$STAGE/start.sh"

cat > "$STAGE/VERSION.txt" <<EOF
DB-care v${VERSION}
Build date: $(date '+%Y-%m-%d %H:%M:%S')
EOF

echo "[5/5] zip 압축..."
rm -f "$ZIP_PATH"
cd "$BUILD_ROOT"
zip -r -q "$ZIP_PATH" "DB-care"
cd "$ROOT"

SIZE=$(du -h "$ZIP_PATH" | cut -f1)

echo ""
echo "======================================"
echo " 빌드 완료!"
echo ""
echo " 파일 : $ZIP_PATH"
echo " 크기 : $SIZE"
echo "======================================"
echo ""
