"""
DB-care Backend - FastAPI Application
"""
import os
import hmac
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from models.database import engine, Base, create_seed_data, apply_lightweight_migrations
from routers import patients, prediction, scenario, case_comparison, upload, diagnostics

# DB 테이블 생성 + 경량 자동 마이그레이션 (기존 DB 에 새 컬럼 추가)
Base.metadata.create_all(bind=engine)
apply_lightweight_migrations()

app = FastAPI(
    title="DB-care API",
    description="당뇨 합병증 예측 프로그램 백엔드",
    version="2.2.3",
)

REQUIRED_API_TOKEN = os.environ.get("DBCARE_API_TOKEN", "").strip()
PUBLIC_PATHS = {"/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if request.method == "OPTIONS" or path in PUBLIC_PATHS:
        return await call_next(request)

    if not path.startswith("/api/"):
        return await call_next(request)

    # Development compatibility: plain uvicorn/npm dev runs can omit the token.
    if not REQUIRED_API_TOKEN:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)

    supplied_token = auth_header[7:].strip()
    if not hmac.compare_digest(
        supplied_token.encode("utf-8"), REQUIRED_API_TOKEN.encode("utf-8")
    ):
        return JSONResponse({"detail": "Invalid token"}, status_code=401)

    return await call_next(request)

# CORS (개발 시 Vite, 프로덕션 시 동일 오리진)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(patients.router)
app.include_router(prediction.router)
app.include_router(scenario.router)
app.include_router(case_comparison.router)
app.include_router(upload.router)
app.include_router(diagnostics.router)


@app.get("/health")
def health_check():
    # instance_id: Tauri shell 이 spawn 시 DBCARE_INSTANCE_ID 환경변수로 주입.
    # 점유된 8765 포트의 backend 가 자기(현 Tauri) 인스턴스인지 좀비/타서버인지
    # 구별하기 위해 echo. PUBLIC_PATHS 라 미인증으로도 호출 가능.
    return {
        "status": "ok",
        "service": "DB-care API",
        "version": "2.2.3",
        "instance_id": os.environ.get("DBCARE_INSTANCE_ID"),
    }


@app.on_event("startup")
def on_startup():
    create_seed_data()


# -----------------------------------------------------------
# 프로덕션 모드: 빌드된 프론트엔드 정적 파일 서빙
# -----------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# 배포 zip 에서는 frontend_dist 폴더로 패키징됨
# 개발 소스에서는 frontend/dist 를 사용
_FRONTEND_CANDIDATES = [
    PROJECT_ROOT / "frontend_dist",
    PROJECT_ROOT / "frontend" / "dist",
]
FRONTEND_DIST = next((p for p in _FRONTEND_CANDIDATES if p.exists()), None)
INDEX_HEADERS = {"Cache-Control": "no-store"}


def _json_for_script(value: str) -> str:
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _token_script() -> str:
    token = _json_for_script(REQUIRED_API_TOKEN)
    return (
        '<script id="dbcare-api-token">'
        "(function(){"
        f"var token={token};"
        "if(typeof window.__DBCARE_TOKEN__==='string'&&window.__DBCARE_TOKEN__){return;}"
        "Object.defineProperty(window,'__DBCARE_TOKEN__',{"
        "value:token,writable:false,configurable:false,enumerable:false"
        "});"
        "})();"
        "</script>"
    )


def _index_response():
    index_path = FRONTEND_DIST / "index.html"
    if not REQUIRED_API_TOKEN:
        return FileResponse(str(index_path), headers=INDEX_HEADERS)

    html = index_path.read_text(encoding="utf-8")
    lower_html = html.lower()
    head_pos = lower_html.find("<head")
    if head_pos != -1:
        insert_at = html.find(">", head_pos) + 1
        if insert_at > 0:
            html = f"{html[:insert_at]}\n    {_token_script()}{html[insert_at:]}"
        else:
            html = f"{_token_script()}\n{html}"
    else:
        html = f"{_token_script()}\n{html}"

    return Response(html, media_type="text/html", headers=INDEX_HEADERS)

if FRONTEND_DIST is not None:
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def _serve_root_index():
        return _index_response()

    @app.get("/{full_path:path}")
    def _serve_spa(full_path: str):
        """
        React Router 용 SPA fallback.
        정적 파일이 있으면 해당 파일을, 없으면 index.html 반환.
        /api 경로는 이 핸들러에 도달하기 전에 라우터가 처리함.
        """
        # API 및 기타 경로는 기본 404 처리
        if full_path.startswith("api/") or full_path.startswith("health"):
            return _index_response()

        requested = FRONTEND_DIST / full_path
        if requested.is_file():
            return FileResponse(str(requested))

        # SPA fallback
        return _index_response()
