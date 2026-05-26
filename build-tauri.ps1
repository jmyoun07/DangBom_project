# ==========================================================
#  DB-care Tauri Build (End-to-End)
#  .\build-tauri.ps1
#
#  단계:
#    1) Python backend sidecar 빌드 (PyInstaller → dist\dbcare-backend\)
#    2) Backend 폴더 → src-tauri\resources\dbcare-backend\ 복사
#    3) Frontend 빌드 (npm run build → frontend\dist\)
#    4) Tauri 빌드 (cargo tauri build → src-tauri\target\release\bundle\)
#
#  결과물:  src-tauri\target\release\bundle\nsis\DB-care_2.1.1_x64-setup.exe
#          또는 src-tauri\target\release\bundle\msi\DB-care_2.1.1_x64_ko-KR.msi
# ==========================================================

# 'Continue' — native exe(특히 PyInstaller)가 stderr 로 진행 메시지를 내보내면
# 'Stop' 모드에서는 NativeCommandError 로 던져져 빌드가 일찍 죽는다.
# 각 단계마다 $LASTEXITCODE 를 명시적으로 체크하므로 'Continue' 로 충분히 안전.
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
$Version = '2.1.5'

# Rust 가 새로 설치된 경우 PATH 갱신 (cargo / tauri-cli 위치)
$cargoBin = "$env:USERPROFILE\.cargo\bin"
if (Test-Path "$cargoBin\cargo.exe") {
    $env:PATH = "$cargoBin;$env:PATH"
}

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host " DB-care Tauri Builder v$Version" -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ''

# --- [1/4] Backend sidecar 빌드 ---
Write-Host '[1/4] PyInstaller 로 backend sidecar 빌드...' -ForegroundColor Yellow
$backendDist = Join-Path $Root 'dist\dbcare-backend'
if (Test-Path $backendDist) {
    Write-Host '    기존 빌드 제거...' -ForegroundColor DarkGray
    Remove-Item $backendDist -Recurse -Force
}
& python -m PyInstaller --noconfirm 'dbcare-backend.spec'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller backend 빌드 실패' }
if (-not (Test-Path (Join-Path $backendDist 'dbcare-backend.exe'))) {
    throw "Backend exe 생성 실패: $backendDist\dbcare-backend.exe"
}
Write-Host "    OK: $backendDist\dbcare-backend.exe" -ForegroundColor Green

# --- [2/4] Backend → Tauri resources 복사 ---
Write-Host ''
Write-Host '[2/4] Backend 폴더를 Tauri resources 로 복사...' -ForegroundColor Yellow
$tauriResources = Join-Path $Root 'src-tauri\resources\dbcare-backend'
if (Test-Path $tauriResources) {
    Remove-Item $tauriResources -Recurse -Force
}
New-Item -ItemType Directory -Path $tauriResources -Force | Out-Null
Copy-Item -Path "$backendDist\*" -Destination $tauriResources -Recurse -Force
$resourceSizeMB = [math]::Round((Get-ChildItem $tauriResources -Recurse | Measure-Object Length -Sum).Sum / 1MB, 2)
Write-Host "    복사 완료: $tauriResources ($resourceSizeMB MB)" -ForegroundColor Green

# --- [3/4] Frontend 빌드 ---
Write-Host ''
Write-Host '[3/4] Frontend 빌드 (npm run build)...' -ForegroundColor Yellow
Push-Location (Join-Path $Root 'frontend')
try {
    # PowerShell `& npm` 은 .cmd shim 인자 처리 이슈가 있어서 명시적으로 호출
    cmd /c "npm run build"
    if ($LASTEXITCODE -ne 0) { throw 'frontend 빌드 실패' }
} finally {
    Pop-Location
}
Write-Host "    OK: frontend\dist" -ForegroundColor Green

# --- [4/4] Tauri 빌드 ---
Write-Host ''
Write-Host '[4/4] Tauri 빌드 (cargo tauri build)...' -ForegroundColor Yellow
Push-Location $Root
try {
    & cargo tauri build
    if ($LASTEXITCODE -ne 0) { throw 'Tauri 빌드 실패' }
} finally {
    Pop-Location
}

# --- 결과물 확인 ---
$bundleDir = Join-Path $Root 'src-tauri\target\release\bundle'
$nsisExe = Get-ChildItem -Path (Join-Path $bundleDir 'nsis') -Filter '*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
$msiFile = Get-ChildItem -Path (Join-Path $bundleDir 'msi') -Filter '*.msi' -ErrorAction SilentlyContinue | Select-Object -First 1

Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host ' BUILD SUCCESS' -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
Write-Host ''
if ($nsisExe) {
    $nsisSize = [math]::Round($nsisExe.Length / 1MB, 2)
    Write-Host "  NSIS 설치 프로그램 : $($nsisExe.FullName)" -ForegroundColor White
    Write-Host "  크기              : $nsisSize MB" -ForegroundColor White
}
if ($msiFile) {
    $msiSize = [math]::Round($msiFile.Length / 1MB, 2)
    Write-Host "  MSI 설치 프로그램  : $($msiFile.FullName)" -ForegroundColor White
    Write-Host "  크기              : $msiSize MB" -ForegroundColor White
}
Write-Host ''
Write-Host '배포 방법:' -ForegroundColor Cyan
Write-Host '  1) 위 .exe / .msi 를 USB / 네트워크 드라이브로 복사'
Write-Host '  2) 다른 PC 에서 더블클릭 → 설치 마법사 시작'
Write-Host '  3) 설치 후 바탕화면 / 시작메뉴에서 DB-care 실행'
Write-Host '     (단일 윈도우, 127.0.0.1 노출 없음)'
Write-Host ''
