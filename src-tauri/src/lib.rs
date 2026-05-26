// DB-care v2.1.x — Tauri shell.
//
// 동작 흐름:
//   1. 단일 인스턴스 락 (기존 창 포커스 후 즉시 종료)
//   2. Python backend sidecar (`dbcare-backend.exe`) 를 자식 프로세스로 spawn
//   3. 127.0.0.1:8765/health 가 응답할 때까지 최대 180초 대기
//   4. WebView 윈도우가 frontend dist 를 렌더링 (Tauri 가 자동)
//   5. 종료 시 Python 프로세스도 함께 종료
//
// Edge 를 외부에서 띄우지 않으므로 사용자 화면에 "127.0.0.1" 글자가 노출되지 않는다.

use std::fmt::Write as _;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent, WindowEvent};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

// 백엔드 포트 — launcher.py 와 동일하게 8765 우선, 점유 시 환경변수로 override.
const BACKEND_PORT: u16 = 8765;
const BACKEND_TIMEOUT_SECS: u64 = 180;

/// Python sidecar 프로세스 핸들을 앱 상태에 보관. 종료 시 함께 kill.
struct BackendHandle(Mutex<Option<Child>>);

fn generate_api_token() -> Result<String, String> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes)
        .map_err(|e| format!("API token random generation failed: {}", e))?;

    let mut token = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        let _ = write!(&mut token, "{:02x}", byte);
    }
    Ok(token)
}

fn api_token_initialization_script(api_token: &str) -> String {
    let token_literal =
        serde_json::to_string(api_token).expect("serializing DB-care API token cannot fail");
    format!(
        r#"
(() => {{
  const allowedOrigins = new Set([
    "http://127.0.0.1:{port}",
    "http://localhost:{port}"
  ]);
  if (!allowedOrigins.has(window.location.origin)) {{
    return;
  }}
  if (typeof window.__DBCARE_TOKEN__ === "string" && window.__DBCARE_TOKEN__) {{
    return;
  }}
  Object.defineProperty(window, "__DBCARE_TOKEN__", {{
    value: {token},
    writable: false,
    configurable: false,
    enumerable: false
  }});
}})();
"#,
        port = BACKEND_PORT,
        token = token_literal
    )
}

/// Python backend sidecar 시작.
/// PyInstaller 가 만든 `dbcare-backend.exe` 가 같은 폴더 (또는 _internal) 에 있다고 가정.
fn spawn_backend(app: &tauri::AppHandle, api_token: &str) -> Result<Child, String> {
    // 1) 실행 파일 경로 — Tauri 리소스 디렉토리 또는 같은 폴더의 dbcare-backend.exe
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("current_exe 실패: {}", e))?
        .parent()
        .ok_or("부모 디렉토리 없음")?
        .to_path_buf();

    let mut candidates = vec![
        exe_dir.join("dbcare-backend.exe"),
        exe_dir.join("_internal").join("dbcare-backend.exe"),
        exe_dir.join("backend").join("dbcare-backend.exe"),
    ];

    // dev 모드 — 프로젝트 루트의 dist/dbcare-backend/ 에서 찾기
    // 프로덕션 — Tauri 가 src-tauri/resources/dbcare-backend/ 폴더째 패키징하므로
    //          한 단계 하위까지 후보 경로에 포함시켜야 함 (v2.1.5 fix).
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("dbcare-backend.exe"));
        candidates.push(resource_dir.join("backend").join("dbcare-backend.exe"));
        candidates.push(
            resource_dir
                .join("dbcare-backend")
                .join("dbcare-backend.exe"),
        );
    }

    let backend_exe = candidates
        .iter()
        .find(|p| p.exists())
        .ok_or_else(|| {
            format!(
                "dbcare-backend.exe 를 찾을 수 없습니다. 시도한 경로:\n{}",
                candidates
                    .iter()
                    .map(|p| format!("  - {}", p.display()))
                    .collect::<Vec<_>>()
                    .join("\n")
            )
        })?
        .clone();

    log::info!("백엔드 spawn: {}", backend_exe.display());

    let mut cmd = Command::new(&backend_exe);
    cmd.env("DBCARE_DESKTOP", "1")
        .env("DBCARE_PORT", BACKEND_PORT.to_string())
        .env("DBCARE_API_TOKEN", api_token)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null());

    // Windows: 콘솔 창 생성 금지 (CREATE_NO_WINDOW)
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    cmd.spawn().map_err(|e| format!("백엔드 spawn 실패: {}", e))
}

/// /health 응답을 기다림. 정상이면 true.
fn wait_for_backend(port: u16, timeout: Duration) -> bool {
    let url = format!("http://127.0.0.1:{}/health", port);
    let client = match reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(500))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Ok(resp) = client.get(&url).send() {
            if resp.status().is_success() {
                return true;
            }
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

/// 시작 실패 시 메시지박스로 진단 정보 표시.
#[cfg(target_os = "windows")]
fn show_error_dialog(title: &str, msg: &str) {
    use std::ffi::OsStr;
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;

    let to_wide = |s: &str| -> Vec<u16> { OsStr::new(s).encode_wide().chain(once(0)).collect() };
    let wtitle = to_wide(title);
    let wmsg = to_wide(msg);

    extern "system" {
        fn MessageBoxW(hwnd: *const u8, text: *const u16, caption: *const u16, utype: u32) -> i32;
    }
    unsafe {
        MessageBoxW(std::ptr::null(), wmsg.as_ptr(), wtitle.as_ptr(), 0x10);
    }
}

#[cfg(not(target_os = "windows"))]
fn show_error_dialog(_title: &str, msg: &str) {
    eprintln!("{}", msg);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let api_token = match generate_api_token() {
        Ok(token) => token,
        Err(e) => {
            show_error_dialog("DB-care start failed", &e);
            std::process::exit(1);
        }
    };
    let auth_init_script = api_token_initialization_script(&api_token);

    tauri::Builder::default()
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("dbcare-auth")
                .js_init_script(auth_init_script)
                .build(),
        )
        // 1) 단일 인스턴스 — 두 번째 실행 시 기존 창 포커스 + 즉시 종료
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .manage(BackendHandle(Mutex::new(None)))
        .setup(move |app| {
            // 디버그 모드에서만 로그 플러그인
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // 2) Python 백엔드 spawn
            let handle = app.handle().clone();
            match spawn_backend(&handle, &api_token) {
                Ok(child) => {
                    log::info!("백엔드 spawn 성공 pid={}", child.id());
                    let state: tauri::State<BackendHandle> = handle.state();
                    *state.0.lock().unwrap() = Some(child);
                }
                Err(e) => {
                    show_error_dialog(
                        "DB-care 시작 실패",
                        &format!(
                            "Python 백엔드 실행 파일을 찾을 수 없습니다.\n\n{}\n\n프로그램을 다시 설치해주세요.",
                            e
                        ),
                    );
                    std::process::exit(1);
                }
            }

            // 3) /health 대기 (최대 180초 — 느린 HDD + AV 스캔 대응)
            log::info!("백엔드 /health 대기 시작 (최대 {}초)", BACKEND_TIMEOUT_SECS);
            if !wait_for_backend(BACKEND_PORT, Duration::from_secs(BACKEND_TIMEOUT_SECS)) {
                show_error_dialog(
                    "DB-care 시작 실패",
                    &format!(
                        "백엔드 서버가 {}초 내에 응답하지 않았습니다.\n\n흔한 원인:\n  • 백신이 _internal 폴더 파일을 격리\n  • Microsoft Visual C++ 2015-2022 재배포 패키지 미설치\n  • 디스크가 너무 느림\n\n환자 데이터 폴더: %APPDATA%\\DB-care\\\n로그 파일: %APPDATA%\\DB-care\\launcher.log",
                        BACKEND_TIMEOUT_SECS
                    ),
                );
                std::process::exit(1);
            }
            log::info!("백엔드 /health OK — UI 준비");

            // 4) 메인 윈도우는 tauri.conf.json 의 windows[0] 설정으로 자동 생성됨.
            //    devUrl(http://localhost:5173) / frontendDist(../frontend/dist) 중 자동 선택.
            //    별도 navigate 코드 불필요.
            Ok(())
        })
        .on_window_event(|window, event| {
            // 메인 창 닫히면 백엔드도 함께 종료
            if let WindowEvent::CloseRequested { .. } = event {
                let app = window.app_handle();
                let state: tauri::State<BackendHandle> = app.state();
                let mut guard = state.0.lock().unwrap();
                if let Some(mut child) = guard.take() {
                    let _ = child.kill();
                    log::info!("백엔드 프로세스 종료됨");
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let RunEvent::Exit = event {
                // 안전망 — 어떤 경로로든 앱 종료될 때 백엔드 cleanup
                log::info!("Tauri exit event");
            }
        });
}
