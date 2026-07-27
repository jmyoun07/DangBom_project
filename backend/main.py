"""
DB-care Backend - FastAPI Application
"""
import os
import hmac
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from models.database import engine, Base, create_seed_data, apply_lightweight_migrations, DB_FILE
from routers import patients, prediction, scenario, case_comparison, upload, diagnostics, graduates

# DB 테이블 생성 + 경량 자동 마이그레이션 (기존 DB 에 새 컬럼 추가)
Base.metadata.create_all(bind=engine)
apply_lightweight_migrations()


def _attach_file_log() -> None:
    """설치본(--windowed PyInstaller)은 stdout/stderr 이 devnull 이라 traceback 이 증발한다.
    실제 배포 PC 에서 500 원인을 사후에 확인할 수 있도록 DB 폴더의 backend.log 에 남긴다.
    (backend_entry.py 가 쓰는 %APPDATA%\\DB-care\\backend.log 와 같은 파일)"""
    logger = logging.getLogger("dbcare")
    logger.setLevel(logging.INFO)
    log_path = Path(DB_FILE).parent / "backend.log"
    if any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", None) == str(log_path)
        for h in logger.handlers
    ):
        return
    try:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except Exception:
        pass  # 로그 파일을 못 열어도 앱은 정상 동작해야 한다


_attach_file_log()

app = FastAPI(
    title="DB-care API",
    description="당뇨 합병증 예측 프로그램 백엔드",
    version="2.4.0",
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
        return JSONResponse(
            {"error": "Authentication required", "detail": "Authentication required", "success": False},
            status_code=401,
        )

    supplied_token = auth_header[7:].strip()
    if not hmac.compare_digest(
        supplied_token.encode("utf-8"), REQUIRED_API_TOKEN.encode("utf-8")
    ):
        return JSONResponse(
            {"error": "Invalid token", "detail": "Invalid token", "success": False},
            status_code=401,
        )

    return await call_next(request)


# ── v2.3.0 (감사): 에러 응답 규격 통일 ──
# CLAUDE.md 코딩 원칙은 {"error": ..., "detail": ...} 를 규정하지만 FastAPI 기본
# HTTPException 은 {"detail": ...} 만 반환했다. 기존 프론트가 detail 을 파싱하므로
# detail 키는 유지하고 error/success 키를 추가하는 방식(하위호환)으로 통일한다.
@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    error_msg = detail if isinstance(detail, str) else "요청을 처리하지 못했습니다."
    return JSONResponse(
        {"error": error_msg, "detail": jsonable_encoder(detail), "success": False},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    # detail 은 하위호환용 원본 배열, error 는 사람이 읽는 한 줄 요약(프론트 표시용).
    errors = exc.errors()
    summary = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', [])[1:]) or '입력'}: {e.get('msg', '')}"
        for e in errors[:3]
    ) or "입력값 검증에 실패했습니다."
    return JSONResponse(
        {"error": f"입력값 검증 실패 — {summary}", "detail": jsonable_encoder(errors), "success": False},
        status_code=422,
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """예상치 못한 500 도 동일 에러 규격으로 반환 (기본 text/plain 대신 JSON)."""
    logging.getLogger("dbcare").exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        {
            "error": "서버 내부 오류가 발생했습니다.",
            "detail": f"{type(exc).__name__}: {exc}",
            "success": False,
        },
        status_code=500,
    )

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
app.include_router(graduates.router)


@app.get("/health")
def health_check():
    # instance_id: Tauri shell 이 spawn 시 DBCARE_INSTANCE_ID 환경변수로 주입.
    # 점유된 8765 포트의 backend 가 자기(현 Tauri) 인스턴스인지 좀비/타서버인지
    # 구별하기 위해 echo. PUBLIC_PATHS 라 미인증으로도 호출 가능.
    return {
        "status": "ok",
        "service": "DB-care API",
        "version": "2.4.0",
        "instance_id": os.environ.get("DBCARE_INSTANCE_ID"),
    }


@app.on_event("startup")
def on_startup():
    create_seed_data()
    # 병원이 갱신하는 졸업자 raw 데이터셋(csv/xlsx)을 기동 시 자동 반영.
    #   내용이 바뀐 경우에만 재적재하므로(해시 비교) 매번 덮어쓰지 않는다.
    try:
        from models.database import SessionLocal
        from services.graduates import sync_from_project_file
        db = SessionLocal()
        try:
            # PROJECT_ROOT 는 아래(정적 서빙 블록)에서 정의되므로 여기서 직접 계산 —
            #   모듈 로드 순서에 의존하지 않게 한다.
            res = sync_from_project_file(db, Path(__file__).resolve().parent.parent)
            if res["status"] == "loaded":
                logging.getLogger("dbcare").info(
                    "졸업자 데이터 갱신: %s → %d명", res["file"], res["loaded"])
            elif res["status"] == "failed":
                logging.getLogger("dbcare").warning(
                    "졸업자 파일 파싱 실패(기존 데이터 유지): %s", res["file"])
        finally:
            db.close()
    except Exception:
        logging.getLogger("dbcare").exception("졸업자 자동 동기화 실패(기존 데이터 유지)")


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
        # v2.3.0 (감사): 라우터가 처리하지 못한 /api·/health 경로는 index.html(200) 대신
        #   JSON 404 를 반환 — API 클라이언트가 HTML 을 성공 응답으로 오인하지 않게 한다.
        #   경계는 정확히 세그먼트 단위로 판정한다 ('/api' 자체는 포함, '/healthcare' 같은
        #   SPA 경로는 제외 — 이전 startswith("health") 는 과하게 넓었다).
        _seg = full_path.split("/", 1)[0]
        if _seg in ("api", "health"):
            return JSONResponse(
                {
                    "error": "Not Found",
                    "detail": f"존재하지 않는 API 경로입니다: /{full_path}",
                    "success": False,
                },
                status_code=404,
            )

        requested = FRONTEND_DIST / full_path
        if requested.is_file():
            return FileResponse(str(requested))

        # SPA fallback
        return _index_response()
