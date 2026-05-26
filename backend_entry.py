"""
DB-care Backend Sidecar Entry Point (Tauri 마이그레이션용).

Tauri Rust shell 이 이 exe 를 자식 프로세스로 spawn 한다.
역할은 FastAPI 백엔드를 127.0.0.1:8765 에 띄우는 것뿐.
단일 인스턴스 락 / 브라우저 실행 / 진단 메시지박스는 모두 Tauri 측에서 처리.
"""
from __future__ import annotations

import os
import sys
import multiprocessing

# ────────────────────────────────────────────────────────────
# CRITICAL: PyInstaller frozen + joblib(loky) 워커 spawn 차단.
# Tauri sidecar 로 분리되어도 ML 모델이 worker 를 spawn 하려고 시도하므로
# 반드시 import 전에 호출.
# ────────────────────────────────────────────────────────────
multiprocessing.freeze_support()

# 자식 프로세스 감지 — joblib 등이 sys.executable 재실행으로 부르면 즉시 종료.
_CHILD_FLAG = "DBCARE_BACKEND_PARENT_PID"
if os.environ.get(_CHILD_FLAG):
    sys.exit(0)
os.environ[_CHILD_FLAG] = str(os.getpid())

# ────────────────────────────────────────────────────────────
# stdout/stderr 안전화 — --windowed 빌드는 콘솔 핸들이 None.
# ────────────────────────────────────────────────────────────
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import time
import traceback
from pathlib import Path

# ────────────────────────────────────────────────────────────
# 경로 — PyInstaller onedir 모드 호환
# ────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    BASE_DIR = Path(__file__).resolve().parent

BACKEND_DIR = BASE_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# APPDATA — 환자 DB / 로그
_APPDATA = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
APP_ROOT = _APPDATA / "DB-care"
APP_ROOT.mkdir(parents=True, exist_ok=True)
LOG_PATH = APP_ROOT / "backend.log"


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def main() -> None:
    _log("===== DB-care backend sidecar 시작 =====")
    _log(f"frozen={getattr(sys, 'frozen', False)}, BASE_DIR={BASE_DIR}")

    port = int(os.environ.get("DBCARE_PORT", "8765"))
    os.environ.setdefault("DBCARE_DESKTOP", "1")

    try:
        import uvicorn
        from main import app  # type: ignore
    except BaseException as e:
        tb = traceback.format_exc()
        _log(f"백엔드 import 실패: {type(e).__name__}: {e}")
        _log(tb)
        sys.exit(2)

    try:
        _log(f"uvicorn 시작 port={port}")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    except BaseException as e:
        tb = traceback.format_exc()
        _log(f"uvicorn 실행 실패: {type(e).__name__}: {e}")
        _log(tb)
        sys.exit(3)


if __name__ == "__main__":
    main()
