"""
DB-care Desktop Launcher
========================
FastAPI 백엔드를 백그라운드 스레드로 시작하고, Edge/Chrome 을 `--app` 모드로
띄워 네이티브 앱처럼 표시한다. 브라우저가 없으면 pywebview 로, 그것도 안 되면
기본 브라우저로 fallback.

WebView2 0x8007139F 처럼 런타임이 깨진 환경에서도 동작하도록 3단계 fallback.

개발 실행:
    python launcher.py

패키지 빌드:
    build-exe.ps1 → dist/DB-care/DB-care.exe
"""
from __future__ import annotations

import os
import sys
import secrets
import multiprocessing

# ────────────────────────────────────────────────────────────
# ★★★ CRITICAL: PyInstaller frozen + joblib(loky) 워커 spawn 차단 ★★★
# ────────────────────────────────────────────────────────────
# EasyEnsembleClassifier / sklearn Parallel 등은 predict_proba 시 내부적으로
# joblib.Parallel 로 워커 프로세스를 spawn 한다. Windows + PyInstaller 환경에선
# 워커가 sys.executable (= DB-care.exe) 을 재실행하므로, freeze_support() 가
# 없으면 워커 프로세스가 launcher.main() 을 다시 돌려서 새 Edge 창이 자꾸 뜬다
# (= "127.0.0.1 페이지가 자꾸 뜨는" 증상의 근본 원인).
#
# 반드시 다른 무거운 import (uvicorn, sklearn 등) 보다 먼저 호출해야 한다.
multiprocessing.freeze_support()

# 자식 프로세스 검출용 환경변수 — 만약 freeze_support 가 못 잡은 경로가 있어도
# 자식이 main() 을 통째로 돌리는 것을 한 번 더 막는다.
_DBCARE_CHILD_FLAG = "DBCARE_LAUNCHER_PARENT_PID"
_PARENT_PID_ENV = os.environ.get(_DBCARE_CHILD_FLAG)
if _PARENT_PID_ENV:
    # 우리는 joblib/multiprocessing 워커. 어떤 GUI / 서버도 띄우지 말고 즉시 빠진다.
    # (joblib loky 워커는 자체 진입점에서 작업을 받아 처리하므로 main() 호출 자체가 사고)
    sys.exit(0)
os.environ[_DBCARE_CHILD_FLAG] = str(os.getpid())

# PyInstaller/browser fallback compatibility. Do not log this value.
_LAUNCHER_API_TOKEN = os.environ.get("DBCARE_API_TOKEN", "").strip()
if not _LAUNCHER_API_TOKEN:
    _LAUNCHER_API_TOKEN = secrets.token_hex(32)
os.environ["DBCARE_API_TOKEN"] = _LAUNCHER_API_TOKEN

# ────────────────────────────────────────────────────────────
# stdout/stderr 안전화 — PyInstaller --windowed 모드 대응
# ────────────────────────────────────────────────────────────
# --windowed 로 빌드된 exe 는 콘솔이 없으므로 sys.stdout/stderr 가 None.
# uvicorn 의 DefaultFormatter 가 sys.stdout.isatty() 를 호출하다가
# AttributeError: 'NoneType' object has no attribute 'isatty' 로 죽는다.
# 다른 라이브러리도 stdout 메서드를 직접 부를 수 있으므로 처음부터 더미로 교체.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import time
import socket
import shutil
import threading
import subprocess
import urllib.request
import webbrowser
from pathlib import Path


# ────────────────────────────────────────────────────────────
# 경로 설정 (PyInstaller onedir 모드 호환)
# ────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    BASE_DIR = Path(__file__).resolve().parent

BACKEND_DIR = BASE_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# APPDATA 위치 — 브라우저 --user-data-dir, WebView2 user data 등에 사용
_APPDATA = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
APP_ROOT = _APPDATA / "DB-care"
APP_ROOT.mkdir(parents=True, exist_ok=True)
BROWSER_USER_DATA = APP_ROOT / "BrowserApp"
WV2_USER_DATA = APP_ROOT / "WebView2"
BROWSER_USER_DATA.mkdir(parents=True, exist_ok=True)
WV2_USER_DATA.mkdir(parents=True, exist_ok=True)

# pywebview fallback 용 — WebView2 user data 폴더 env var
os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(WV2_USER_DATA))
# stale lock 제거 (이전 세션 비정상 종료 대비)
for lock_name in ("EBWebView.lock", "EBWebView.Lock", "lockfile"):
    lp = WV2_USER_DATA / lock_name
    try:
        if lp.exists():
            lp.unlink()
    except Exception:
        pass

import traceback  # noqa: E402

# ────────────────────────────────────────────────────────────
# 로그 파일 — 백엔드 startup 실패 시 진짜 원인 기록
# ────────────────────────────────────────────────────────────
LOG_PATH = APP_ROOT / "launcher.log"


def _log(msg: str) -> None:
    """타임스탬프 prefix 로 launcher.log 에 추가."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# 백엔드 startup 이 실패한 진짜 예외를 메인 스레드가 읽을 수 있게 저장
_BACKEND_ERROR: list[str] = []


import uvicorn  # noqa: E402


# ────────────────────────────────────────────────────────────
# 포트 선택
# ────────────────────────────────────────────────────────────
def _pick_port(preferred: int = 8765) -> int:
    try:
        s = socket.socket()
        s.bind(("127.0.0.1", preferred))
        s.close()
        return preferred
    except OSError:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port


PORT = _pick_port(8765)


# ────────────────────────────────────────────────────────────
# 서버 준비 대기
# ────────────────────────────────────────────────────────────
def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    start = time.time()
    url = f"http://127.0.0.1:{port}/health"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _collect_diag_info() -> dict:
    """
    시작 실패 시 메시지박스에 표시할 환경 진단 정보.
    원격 PC 라 로그 회수가 어려우므로 사용자가 IT 에게 그대로 캡처해 보낼 수 있게.
    """
    info: dict[str, str] = {}
    try:
        import platform
        info["win"] = platform.platform()
    except Exception:
        info["win"] = "?"

    # VC++ 2015-2022 x64 Runtime
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as k:
            installed = winreg.QueryValueEx(k, "Installed")[0]
            ver = winreg.QueryValueEx(k, "Version")[0]
            info["vc"] = f"{ver} {'OK' if installed == 1 else 'MISSING'}"
    except Exception:
        info["vc"] = "MISSING"

    # WebView2 Runtime
    try:
        import winreg
        for hive, path in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ):
            try:
                with winreg.OpenKey(hive, path) as k:
                    info["webview2"] = winreg.QueryValueEx(k, "pv")[0]
                    break
            except OSError:
                continue
        else:
            info["webview2"] = "MISSING"
    except Exception:
        info["webview2"] = "?"

    # Edge 실행 파일
    try:
        info["edge"] = "OK" if _find_browser() else "MISSING"
    except Exception:
        info["edge"] = "?"

    # 메모리
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        info["ram"] = f"{stat.ullTotalPhys // (1024 * 1024)} MB"
    except Exception:
        info["ram"] = "?"

    return info


# ────────────────────────────────────────────────────────────
# 백엔드 스레드
# ────────────────────────────────────────────────────────────
def _run_backend():
    """백엔드를 백그라운드 스레드에서 실행. 예외는 _BACKEND_ERROR 에 기록."""
    try:
        _log(f"백엔드 import 시작 (BACKEND_DIR={BACKEND_DIR})")
        from main import app  # type: ignore

        os.environ.setdefault("DBCARE_DESKTOP", "1")
        _log(f"uvicorn 시작 (port={PORT})")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            access_log=False,
        )
    except BaseException as e:
        tb = traceback.format_exc()
        _BACKEND_ERROR.append(f"{type(e).__name__}: {e}\n\n{tb}")
        _log(f"백엔드 실패: {type(e).__name__}: {e}")
        _log(tb)


# ────────────────────────────────────────────────────────────
# Edge/Chrome --app 모드 (1순위 — 가장 안정적)
# ────────────────────────────────────────────────────────────
def _find_browser() -> str | None:
    """Edge 우선, Chrome 순서로 설치된 경로 탐색."""
    candidates = []

    # Edge 기본 경로
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    localappdata = os.environ.get("LOCALAPPDATA", "")

    candidates.extend([
        Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(pf86) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ])
    if localappdata:
        candidates.append(Path(localappdata) / "Google" / "Chrome" / "Application" / "chrome.exe")

    # PATH 에 있으면 그것도 시도
    for name in ("msedge", "chrome"):
        which = shutil.which(name)
        if which:
            candidates.insert(0, Path(which))

    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def _launch_browser_app(url: str) -> subprocess.Popen | None:
    """Edge/Chrome 을 --app 모드로 실행 — 주소창/탭 없는 네이티브 앱 형태."""
    browser = _find_browser()
    if not browser:
        return None

    args = [
        browser,
        f"--app={url}",
        f"--user-data-dir={BROWSER_USER_DATA}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=TranslateUI,MediaRouter",
        f"--window-size=1440,900",
    ]
    try:
        # stdout/stderr 억제 (Chrome 의 디버그 로그 방지)
        CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc
    except Exception as e:
        print(f"[WARN] 브라우저 --app 실행 실패: {e}")
        return None


# ────────────────────────────────────────────────────────────
# pywebview (2순위 — WebView2 필요)
# ────────────────────────────────────────────────────────────
def _start_pywebview(url: str) -> bool:
    try:
        import webview  # noqa
    except Exception as e:
        print(f"[WARN] pywebview import 실패: {e}")
        return False

    try:
        webview.create_window(
            title="DB-care — 당뇨 합병증 예측 프로그램",
            url=url,
            width=1440,
            height=900,
            min_size=(1200, 720),
            resizable=True,
            text_select=True,
            confirm_close=False,
        )
    except Exception as e:
        print(f"[WARN] pywebview create_window 실패: {e}")
        return False

    gui_candidates = ["edgechromium", "mshtml", None] if sys.platform == "win32" else [None]
    for gui in gui_candidates:
        try:
            webview.start(gui=gui, debug=False, private_mode=False)
            return True
        except Exception as e:
            print(f"[WARN] pywebview gui={gui} 실패: {e}")
    return False


# ────────────────────────────────────────────────────────────
# 기본 브라우저 (최후 fallback)
# ────────────────────────────────────────────────────────────
def _open_default_browser_and_wait(url: str):
    try:
        webbrowser.open(url)
        print(f"[INFO] 기본 브라우저로 열었습니다: {url}")
        print("[INFO] 종료하려면 이 콘솔 창을 닫으세요 (Ctrl+C).")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)


# ────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────
def _acquire_single_instance_lock() -> bool:
    """
    이미 다른 DB-care 인스턴스가 떠 있는지 검사. 떠 있으면 False.

    구현: APP_ROOT/launcher.lock 파일을 독점 모드로 연다 (msvcrt.locking).
    프로세스 종료 시 OS 가 자동으로 락을 해제하므로 stale lock 문제가 없다.
    """
    lock_path = APP_ROOT / "launcher.lock"
    try:
        # 'w+' 로 열어 OS 핸들 유지 (모듈 전역에 보관해야 GC 로 닫히지 않음)
        global _SINGLE_INSTANCE_FH
        _SINGLE_INSTANCE_FH = open(lock_path, "w")
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(_SINGLE_INSTANCE_FH.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                _SINGLE_INSTANCE_FH.close()
                _SINGLE_INSTANCE_FH = None
                return False
        else:
            import fcntl
            try:
                fcntl.flock(_SINGLE_INSTANCE_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                _SINGLE_INSTANCE_FH.close()
                _SINGLE_INSTANCE_FH = None
                return False
        # 우리 PID 기록 (디버깅용)
        try:
            _SINGLE_INSTANCE_FH.write(str(os.getpid()))
            _SINGLE_INSTANCE_FH.flush()
        except Exception:
            pass
        return True
    except Exception as e:
        _log(f"단일 인스턴스 락 실패(무시하고 진행): {e}")
        return True


_SINGLE_INSTANCE_FH = None


def main():
    _log("===== DB-care launcher 시작 =====")
    _log(f"frozen={getattr(sys, 'frozen', False)}, BASE_DIR={BASE_DIR}")
    _log(f"sys.executable={sys.executable}")

    # 0) 단일 인스턴스 보장 — 이미 떠 있으면 조용히 종료
    if not _acquire_single_instance_lock():
        _log("이미 다른 DB-care 인스턴스가 실행 중. 이 프로세스는 종료.")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "DB-care 가 이미 실행 중입니다.\n작업 표시줄에서 기존 창을 확인하세요.",
                "DB-care",
                0x40,
            )
        except Exception:
            pass
        sys.exit(0)

    # 1) 백엔드 시작
    threading.Thread(target=_run_backend, daemon=True, name="dbcare-backend").start()

    # 2) 서버 준비 대기 — 느린 HDD + AV 스캔 동시에 일어나면 첫 실행이 2~3분 걸릴 수 있어
    # 180초까지 기다린다. 정상 PC 에서는 보통 5~15초.
    if not _wait_for_server(PORT, timeout=180):
        # 백엔드 스레드가 잡은 진짜 예외가 있으면 표시
        detail = _BACKEND_ERROR[0] if _BACKEND_ERROR else "(서버 시작 시간 초과 — 180초 내 응답 없음)"
        first_line = detail.split("\n", 1)[0][:200]

        # 환경 진단 정보 — 원격 PC 라 로그 회수가 어려우므로 메시지박스에 직접 표시.
        diag = _collect_diag_info()
        diag_text = (
            f"  • Windows  : {diag.get('win', '?')}\n"
            f"  • VC++ x64 : {diag.get('vc', '?')}\n"
            f"  • WebView2 : {diag.get('webview2', '?')}\n"
            f"  • Edge     : {diag.get('edge', '?')}\n"
            f"  • RAM      : {diag.get('ram', '?')}"
        )

        # ImportError / DLL load failed 패턴 감지 → AV 격리 가능성 안내
        hint = ""
        d_low = detail.lower()
        if "dll load failed" in d_low or "could not be found" in d_low:
            hint = "\n→ 백신이 _internal 폴더 파일을 격리한 것으로 보입니다.\n   설치 폴더를 백신 예외로 추가하고 재설치하세요.\n"
        elif "importerror" in d_low or "modulenotfounderror" in d_low:
            hint = "\n→ Microsoft Visual C++ 2015-2022 x64 재배포 패키지를 설치하세요.\n   https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
        elif "permission" in d_low or "access" in d_low and "denied" in d_low:
            hint = "\n→ 설치 폴더 권한 문제입니다. 관리자 권한으로 재설치하세요.\n"

        msg = (
            "DB-care 백엔드 서버를 시작할 수 없습니다.\n\n"
            f"오류: {first_line}\n"
            f"{hint}\n"
            "환경:\n"
            f"{diag_text}\n\n"
            f"상세 로그: {LOG_PATH}\n\n"
            "이 메시지를 캡처하여 IT 담당자에게 보내주세요."
        )
        _log(f"=== 시작 실패 ===\n{detail}\n환경: {diag}")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "DB-care 시작 실패", 0x10)
        except Exception:
            print("[ERROR]", msg)
        sys.exit(1)

    url = f"http://127.0.0.1:{PORT}/"

    # 3) UI 실행 — 3단계 fallback
    # ① Edge/Chrome --app 모드 (가장 안정적, 네이티브 앱처럼 보임)
    proc = _launch_browser_app(url)
    if proc is not None:
        print(f"[INFO] Edge/Chrome --app 모드로 실행 중 (pid={proc.pid}).")
        try:
            proc.wait()
        except KeyboardInterrupt:
            try: proc.terminate()
            except Exception: pass
        return

    # ② pywebview (WebView2)
    print("[INFO] 브라우저 --app 모드 실패. pywebview 로 시도합니다...")
    if _start_pywebview(url):
        return

    # ③ 기본 브라우저
    print("[INFO] pywebview 도 실패. 기본 브라우저로 열기...")
    _open_default_browser_and_wait(url)


if __name__ == "__main__":
    main()
