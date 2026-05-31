// DB-care v2.1.x — Tauri shell.
//
// 동작 흐름 (v2.1.7 — codex 런타임 fix #1):
//   1. 단일 인스턴스 락 (기존 창 포커스 후 즉시 종료)
//   2. instance_id (UUID v4) 생성 — backend 와 공유해 좀비 backend 차단
//   3. 8765 포트 점유 확인:
//      - 비어있음 → spawn 진행
//      - 점유 중 + /health instance_id 일치 → 우리 거 (spawn 생략)
//      - 점유 중 + 불일치/오류 → "이전 세션이 정리되지 않았습니다" 안내 후 종료
//   4. Python backend sidecar 를 자식 프로세스로 spawn
//      Windows 한정: Job Object KILL_ON_JOB_CLOSE 로 부모 죽으면 자동 kill
//   5. /health 폴링 — instance_id 일치 + child.try_wait() 로 조기 종료 감지
//   6. WebView 윈도우가 frontend dist 를 렌더링 (Tauri 가 자동)
//   7. CloseRequested / RunEvent::Exit 모두에서 backend kill 안전망
//
// Edge 를 외부에서 띄우지 않으므로 사용자 화면에 "127.0.0.1" 글자가 노출되지 않는다.

use serde::Deserialize;
use std::fmt::Write as _;
use std::io::Read;
use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder, WindowEvent};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

// v2.1.9 (배포 안정성): 8765 고정 → 동적 포트 폴백.
// 8765 가 점유돼 있고 그게 다른 프로세스면 OS 빈 포트를 자동 선택해 충돌을 피한다.
// (기존 개발 PC 의 좀비 backend / dev 서버가 8765 점유해도 정상 기동)
const PREFERRED_PORT: u16 = 8765;
const BACKEND_TIMEOUT_SECS: u64 = 180;

#[derive(Debug, Deserialize)]
struct HealthResponse {
    instance_id: Option<String>,
}

/// 백엔드 기동 계획 — 기존 인스턴스 재사용 vs 새로 spawn(포트 포함).
#[derive(Debug, Clone, Copy)]
enum BackendLaunchPlan {
    UseExisting { port: u16 },
    Spawn { port: u16 },
}

impl BackendLaunchPlan {
    fn port(&self) -> u16 {
        match self {
            Self::UseExisting { port } | Self::Spawn { port } => *port,
        }
    }
}

struct BackendProcess {
    child: Child,
    #[cfg(target_os = "windows")]
    _job: Option<windows_job::JobObject>,
}

/// Python sidecar 프로세스 핸들을 앱 상태에 보관. 종료 시 함께 kill.
struct BackendHandle(Mutex<Option<BackendProcess>>);

#[cfg(target_os = "windows")]
mod windows_job {
    use std::ffi::c_void;
    use std::mem::{size_of, zeroed};
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use std::ptr;

    type Handle = *mut c_void;
    type Bool = i32;
    type Dword = u32;

    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS: i32 = 9;
    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Dword = 0x0000_2000;

    #[repr(C)]
    struct JobObjectBasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: Dword,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: Dword,
        affinity: usize,
        priority_class: Dword,
        scheduling_class: Dword,
    }

    #[repr(C)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    struct JobObjectExtendedLimitInformation {
        basic_limit_information: JobObjectBasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateJobObjectW(lp_job_attributes: *mut c_void, lp_name: *const u16) -> Handle;
        fn SetInformationJobObject(
            h_job: Handle,
            job_object_info_class: i32,
            lp_job_object_info: *mut c_void,
            cb_job_object_info_length: Dword,
        ) -> Bool;
        fn AssignProcessToJobObject(h_job: Handle, h_process: Handle) -> Bool;
        fn CloseHandle(h_object: Handle) -> Bool;
    }

    pub struct JobObject {
        handle: Handle,
    }

    unsafe impl Send for JobObject {}

    impl Drop for JobObject {
        fn drop(&mut self) {
            unsafe {
                let _ = CloseHandle(self.handle);
            }
        }
    }

    pub fn assign_child_to_kill_on_close_job(child: &Child) -> Result<JobObject, String> {
        unsafe {
            let job = CreateJobObjectW(ptr::null_mut(), ptr::null());
            if job.is_null() {
                return Err(format!(
                    "CreateJobObjectW 실패: {}",
                    std::io::Error::last_os_error()
                ));
            }

            let mut info: JobObjectExtendedLimitInformation = zeroed();
            info.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

            if SetInformationJobObject(
                job,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                &mut info as *mut _ as *mut c_void,
                size_of::<JobObjectExtendedLimitInformation>() as Dword,
            ) == 0
            {
                let err = std::io::Error::last_os_error();
                let _ = CloseHandle(job);
                return Err(format!("SetInformationJobObject 실패: {}", err));
            }

            if AssignProcessToJobObject(job, child.as_raw_handle() as Handle) == 0 {
                let err = std::io::Error::last_os_error();
                let _ = CloseHandle(job);
                return Err(format!("AssignProcessToJobObject 실패: {}", err));
            }

            Ok(JobObject { handle: job })
        }
    }
}

#[cfg(target_os = "windows")]
mod windows_dialog {
    use std::ffi::{c_void, OsStr};
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;
    use std::ptr;

    #[link(name = "user32")]
    extern "system" {
        fn MessageBoxW(hwnd: *mut c_void, text: *const u16, caption: *const u16, utype: u32)
            -> i32;
    }

    pub fn show_error(title: &str, msg: &str) {
        let to_wide =
            |s: &str| -> Vec<u16> { OsStr::new(s).encode_wide().chain(once(0)).collect() };
        let wtitle = to_wide(title);
        let wmsg = to_wide(msg);

        unsafe {
            MessageBoxW(ptr::null_mut(), wmsg.as_ptr(), wtitle.as_ptr(), 0x10);
        }
    }
}

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

fn generate_instance_id() -> Result<String, String> {
    let mut bytes = [0u8; 16];
    getrandom::fill(&mut bytes)
        .map_err(|e| format!("instance_id random generation failed: {}", e))?;

    // UUID v4 (RFC 4122): version + variant bits
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;

    let mut id = String::with_capacity(36);
    for (index, byte) in bytes.iter().enumerate() {
        if matches!(index, 4 | 6 | 8 | 10) {
            id.push('-');
        }
        let _ = write!(&mut id, "{:02x}", *byte);
    }
    Ok(id)
}

fn api_token_initialization_script(api_token: &str, port: u16) -> String {
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
        port = port,
        token = token_literal
    )
}

fn build_health_client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(500))
        .build()
        .map_err(|e| format!("health client 생성 실패: {}", e))
}

fn fetch_backend_health(
    client: &reqwest::blocking::Client,
    port: u16,
) -> Result<HealthResponse, String> {
    let url = format!("http://127.0.0.1:{}/health", port);
    let mut resp = client
        .get(&url)
        .send()
        .map_err(|e| format!("/health 요청 실패: {}", e))?;

    let status = resp.status();
    if !status.is_success() {
        return Err(format!("/health HTTP {}", status));
    }

    let mut body = String::new();
    resp.read_to_string(&mut body)
        .map_err(|e| format!("/health 응답 읽기 실패: {}", e))?;

    serde_json::from_str::<HealthResponse>(&body)
        .map_err(|e| format!("/health JSON 파싱 실패: {}", e))
}

/// OS 가 비어있는 포트를 할당하게 한다 (TcpListener bind 0).
fn pick_ephemeral_backend_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|e| format!("빈 백엔드 포트 할당 실패: {}", e))?;
    Ok(listener
        .local_addr()
        .map_err(|e| format!("빈 백엔드 포트 확인 실패: {}", e))?
        .port())
}

/// 백엔드 기동 계획 결정.
///   - 선호 포트(8765) 비어있음 → Spawn(8765)
///   - 선호 포트 점유 + /health instance_id 일치 → UseExisting(8765) (우리 인스턴스, 단일 인스턴스 락)
///   - 선호 포트 점유 + 다른 프로세스 → Spawn(빈 포트)  ※ 종료하지 않고 폴백
fn decide_backend_launch(port: u16, instance_id: &str) -> Result<BackendLaunchPlan, String> {
    match TcpListener::bind(("127.0.0.1", port)) {
        Ok(listener) => {
            drop(listener);
            Ok(BackendLaunchPlan::Spawn { port })
        }
        Err(bind_err) => {
            log::warn!("선호 백엔드 포트 {} 점유 감지: {}", port, bind_err);
            if let Ok(client) = build_health_client() {
                match fetch_backend_health(&client, port) {
                    Ok(h) if h.instance_id.as_deref() == Some(instance_id) => {
                        log::info!("현재 인스턴스 백엔드가 이미 응답 중 — 재사용");
                        return Ok(BackendLaunchPlan::UseExisting { port });
                    }
                    Ok(h) => log::warn!("기존 /health instance_id mismatch: {:?}", h.instance_id),
                    Err(e) => log::warn!("점유 포트 /health 확인 실패: {}", e),
                }
            }
            // 다른 프로세스가 8765 점유 → 빈 포트로 폴백 (종료하지 않음)
            let fallback = pick_ephemeral_backend_port()?;
            log::info!("포트 {} 대신 빈 포트 {} 사용", port, fallback);
            Ok(BackendLaunchPlan::Spawn { port: fallback })
        }
    }
}

/// dbcare-backend.exe 를 dir 하위에서 재귀 탐색 (depth 제한). 어떤 번들 구조든 대응.
fn find_backend_exe_recursive(dir: &std::path::Path, depth: usize) -> Option<std::path::PathBuf> {
    if depth == 0 {
        return None;
    }
    let entries = std::fs::read_dir(dir).ok()?;
    let mut subdirs = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() {
            if path.file_name().and_then(|n| n.to_str()) == Some("dbcare-backend.exe") {
                return Some(path);
            }
        } else if path.is_dir() {
            subdirs.push(path);
        }
    }
    for sub in subdirs {
        if let Some(found) = find_backend_exe_recursive(&sub, depth - 1) {
            return Some(found);
        }
    }
    None
}

/// Python backend sidecar 시작.
/// PyInstaller 가 만든 `dbcare-backend.exe` 가 같은 폴더 (또는 _internal) 에 있다고 가정.
fn spawn_backend(
    app: &tauri::AppHandle,
    api_token: &str,
    instance_id: &str,
    port: u16,
) -> Result<BackendProcess, String> {
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("current_exe 실패: {}", e))?
        .parent()
        .ok_or("부모 디렉토리 없음")?
        .to_path_buf();

    // v2.1.10 (배포 fix): Tauri 2 의 resources(["resources/**/*"]) 는 설치 시
    // <resource_dir>/resources/dbcare-backend/dbcare-backend.exe 로 들어간다.
    // 이전엔 resources/ 세그먼트가 빠진 경로만 탐색해 "찾을 수 없음" 실패.
    // → resources/ 변형 모두 추가 + 못 찾으면 재귀 탐색(depth 4) fallback.
    let mut candidates = vec![
        exe_dir.join("dbcare-backend.exe"),
        exe_dir.join("_internal").join("dbcare-backend.exe"),
        exe_dir.join("dbcare-backend").join("dbcare-backend.exe"),
        exe_dir.join("backend").join("dbcare-backend.exe"),
        exe_dir.join("resources").join("dbcare-backend").join("dbcare-backend.exe"),
    ];

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("dbcare-backend.exe"));
        candidates.push(resource_dir.join("dbcare-backend").join("dbcare-backend.exe"));
        candidates.push(resource_dir.join("backend").join("dbcare-backend.exe"));
        // ★ 핵심: Tauri resources glob 이 유지하는 resources/ 세그먼트 포함 경로
        candidates.push(
            resource_dir
                .join("resources")
                .join("dbcare-backend")
                .join("dbcare-backend.exe"),
        );
    }

    let mut backend_exe = candidates.iter().find(|p| p.exists()).cloned();

    // fallback: 알려진 경로에 없으면 설치 루트/리소스 디렉토리에서 재귀 탐색
    if backend_exe.is_none() {
        let mut roots: Vec<std::path::PathBuf> = vec![exe_dir.clone()];
        if let Ok(rd) = app.path().resource_dir() {
            roots.push(rd);
        }
        for root in &roots {
            if let Some(found) = find_backend_exe_recursive(root, 4) {
                log::info!("재귀 탐색으로 backend 발견: {}", found.display());
                backend_exe = Some(found);
                break;
            }
        }
    }

    let backend_exe = backend_exe.ok_or_else(|| {
        format!(
            "dbcare-backend.exe 를 찾을 수 없습니다. 시도한 경로:\n{}",
            candidates
                .iter()
                .map(|p| format!("  - {}", p.display()))
                .collect::<Vec<_>>()
                .join("\n")
        )
    })?;

    log::info!("백엔드 spawn: {}", backend_exe.display());

    let mut cmd = Command::new(&backend_exe);
    cmd.env("DBCARE_DESKTOP", "1")
        .env("DBCARE_PORT", port.to_string())
        .env("DBCARE_API_TOKEN", api_token)
        .env("DBCARE_INSTANCE_ID", instance_id)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null());

    // Windows: 콘솔 창 생성 금지 (CREATE_NO_WINDOW)
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    let child = cmd.spawn().map_err(|e| format!("백엔드 spawn 실패: {}", e))?;

    #[cfg(target_os = "windows")]
    let job = match windows_job::assign_child_to_kill_on_close_job(&child) {
        Ok(job) => {
            log::info!("백엔드 Job Object 연결됨 (부모 종료 시 자식 자동 kill)");
            Some(job)
        }
        Err(e) => {
            log::warn!("백엔드 Job Object 연결 실패 (best-effort): {}", e);
            None
        }
    };

    Ok(BackendProcess {
        child,
        #[cfg(target_os = "windows")]
        _job: job,
    })
}

/// /health 응답을 기다림. child 가 먼저 종료되거나 instance_id 가 다르면 즉시 false.
fn wait_for_backend(
    child: &mut Child,
    port: u16,
    instance_id: &str,
    timeout: Duration,
) -> bool {
    let client = match build_health_client() {
        Ok(client) => client,
        Err(e) => {
            log::error!("{}", e);
            return false;
        }
    };

    let start = Instant::now();
    while start.elapsed() < timeout {
        // 자식 프로세스가 시작 도중 죽었으면 더 기다릴 필요 없음
        match child.try_wait() {
            Ok(Some(status)) => {
                log::error!("백엔드가 시작 중 종료됨: {}", status);
                return false;
            }
            Ok(None) => {}
            Err(e) => {
                log::error!("백엔드 상태 확인 실패: {}", e);
                return false;
            }
        }

        match fetch_backend_health(&client, port) {
            Ok(health) => match health.instance_id.as_deref() {
                Some(existing) if existing == instance_id => return true,
                Some(existing) => {
                    log::error!(
                        "백엔드 instance_id mismatch: existing={}, current={}",
                        existing,
                        instance_id
                    );
                    return false;
                }
                None => {
                    log::error!("백엔드 /health 응답에 instance_id 가 없습니다.");
                    return false;
                }
            },
            Err(e) => {
                log::debug!("백엔드 /health 대기 중: {}", e);
            }
        }

        std::thread::sleep(Duration::from_millis(250));
    }

    false
}

fn terminate_backend_process(mut backend: BackendProcess, reason: &str) {
    match backend.child.try_wait() {
        Ok(Some(status)) => {
            log::info!(
                "백엔드 프로세스가 이미 종료됨 reason={}, status={}",
                reason,
                status
            );
        }
        Ok(None) => {
            let pid = backend.child.id();
            if let Err(e) = backend.child.kill() {
                log::warn!(
                    "백엔드 프로세스 kill 실패 pid={}, reason={}, err={}",
                    pid,
                    reason,
                    e
                );
            } else {
                log::info!("백엔드 프로세스 kill 요청 pid={}, reason={}", pid, reason);
            }
            let _ = backend.child.wait();
        }
        Err(e) => {
            log::warn!(
                "백엔드 프로세스 상태 확인 실패 reason={}, err={}",
                reason,
                e
            );
            let _ = backend.child.kill();
            let _ = backend.child.wait();
        }
    }
}

fn kill_backend(app: &tauri::AppHandle, reason: &str) {
    let state = app.state::<BackendHandle>();
    let backend = {
        let mut guard = state.0.lock().unwrap();
        guard.take()
    };

    if let Some(backend) = backend {
        terminate_backend_process(backend, reason);
    }
}

/// 시작 실패 시 메시지박스로 진단 정보 표시.
#[cfg(target_os = "windows")]
fn show_error_dialog(title: &str, msg: &str) {
    windows_dialog::show_error(title, msg);
}

#[cfg(not(target_os = "windows"))]
fn show_error_dialog(_title: &str, msg: &str) {
    eprintln!("{}", msg);
}

/// 결정된 포트로 메인 윈도우를 동적 생성한다.
/// 토큰은 initialization_script 로 주입 — 초기 로드 race 없음 (eval 보다 안전).
/// backend /health OK 이후 호출해야 흰화면이 안 뜬다.
fn create_main_window(app: &tauri::App, api_token: &str, port: u16) -> Result<(), String> {
    let url = Url::parse(&format!("http://127.0.0.1:{}/", port))
        .map_err(|e| format!("메인 윈도우 URL 생성 실패: {}", e))?;
    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("DB-care — 당뇨 합병증 예측")
        .inner_size(1440.0, 900.0)
        .min_inner_size(1200.0, 720.0)
        .resizable(true)
        .visible(true)
        .initialization_script(api_token_initialization_script(api_token, port))
        .build()
        .map_err(|e| format!("메인 윈도우 생성 실패: {}", e))?;
    Ok(())
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

    let instance_id = match generate_instance_id() {
        Ok(id) => id,
        Err(e) => {
            show_error_dialog("DB-care start failed", &e);
            std::process::exit(1);
        }
    };

    tauri::Builder::default()
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

            let handle = app.handle().clone();

            // 2) 포트 결정 (8765 우선, 점유 시 빈 포트로 폴백)
            let launch = match decide_backend_launch(PREFERRED_PORT, &instance_id) {
                Ok(plan) => plan,
                Err(e) => {
                    show_error_dialog("DB-care 시작 실패", &e);
                    std::process::exit(1);
                }
            };
            let port = launch.port();

            // 3) 새로 spawn 해야 하면 백엔드 띄우고 /health 대기. 기존 인스턴스면 생략.
            if let BackendLaunchPlan::Spawn { port } = launch {
                let mut backend = match spawn_backend(&handle, &api_token, &instance_id, port) {
                    Ok(backend) => {
                        log::info!("백엔드 spawn 성공 pid={} port={}", backend.child.id(), port);
                        backend
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
                };

                log::info!("백엔드 /health 대기 시작 (port={}, 최대 {}초)", port, BACKEND_TIMEOUT_SECS);
                if !wait_for_backend(
                    &mut backend.child,
                    port,
                    &instance_id,
                    Duration::from_secs(BACKEND_TIMEOUT_SECS),
                ) {
                    terminate_backend_process(backend, "startup health check failed");
                    show_error_dialog(
                        "DB-care 시작 실패",
                        &format!(
                            "백엔드 서버가 {}초 내에 올바르게 응답하지 않았습니다.\n\n흔한 원인:\n  • 백신이 _internal 폴더 파일을 격리\n  • Microsoft Visual C++ 2015-2022 재배포 패키지 미설치\n  • 디스크가 너무 느림\n\n환자 데이터 폴더: %APPDATA%\\DB-care\\\n로그 파일: %APPDATA%\\DB-care\\backend.log",
                            BACKEND_TIMEOUT_SECS
                        ),
                    );
                    std::process::exit(1);
                }
                log::info!("백엔드 /health OK — UI 준비");
                // 기존 검증된 패턴: 변수 바인딩 후 .0 접근 (State Deref).
                let state = handle.state::<BackendHandle>();
                *state.0.lock().unwrap() = Some(backend);
            }

            // 4) 결정된 포트로 메인 윈도우 동적 생성 (토큰은 init script 로 주입)
            if let Err(e) = create_main_window(app, &api_token, port) {
                kill_backend(&handle, "main window creation failed");
                show_error_dialog("DB-care 시작 실패", &e);
                std::process::exit(1);
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // 메인 창 닫히면 backend kill
            if let WindowEvent::CloseRequested { .. } = event {
                let app = window.app_handle();
                kill_backend(&app, "window close");
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                // 안전망 — 어떤 경로로 종료되든 backend cleanup
                kill_backend(app_handle, "tauri exit");
                log::info!("Tauri exit event");
            }
        });
}
