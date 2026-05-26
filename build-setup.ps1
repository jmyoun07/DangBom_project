# ==========================================================
#  DB-care Setup.exe Builder (End-to-End)
#  실행:  .\build-setup.ps1
#
#  단계:
#    1) 프론트엔드 빌드 (npm run build)
#    2) PyInstaller 로 dist\DB-care\ 생성
#    3) Inno Setup 으로 dist\DB-care_Setup_v1.0.0.exe 생성
#
#  결과물:  dist\DB-care_Setup_v1.0.0.exe
#          → 다른 원내 PC 로 복사 후 더블클릭 → 설치 마법사 실행
# ==========================================================

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Version = '2.1.5'

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host " DB-care Installer Builder v$Version" -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ''

# --- [0/3] Inno Setup Compiler 위치 확인 ---
$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 5\ISCC.exe"
)
$ISCC = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $ISCC) {
    Write-Host ''
    Write-Host '❌ Inno Setup 이 설치되어 있지 않습니다.' -ForegroundColor Red
    Write-Host ''
    Write-Host '설치 방법:' -ForegroundColor Yellow
    Write-Host '  1) https://jrsoftware.org/isdl.php 에서 Inno Setup 6 다운로드'
    Write-Host '  2) innosetup-6.x.x.exe 실행 후 기본 옵션으로 설치'
    Write-Host '  3) 설치 완료 후 이 스크립트 다시 실행'
    Write-Host ''
    throw 'Inno Setup (ISCC.exe) not found'
}
Write-Host "ISCC: $ISCC" -ForegroundColor Green
Write-Host ''

# --- [0.5/3] VC++ 2015-2022 재배포 패키지 자동 다운로드 ---
# 클린 윈도우에서는 sklearn/xgboost/numpy DLL 로드 실패 방지용으로
# 인스톨러가 자동으로 VC++ Redist 를 깔게 한다. 빌드 PC 에 한번만 받아두면
# 인스톨러에 자동 번들됨. 이미 있으면 스킵.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Download-Once($url, $path, $label) {
    if (Test-Path $path) {
        $sz = [math]::Round((Get-Item $path).Length / 1MB, 2)
        Write-Host "$label 캐시: $path ($sz MB)" -ForegroundColor Green
        return $true
    }
    Write-Host "$label 다운로드..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $url -OutFile $path -UseBasicParsing
        $sz = [math]::Round((Get-Item $path).Length / 1MB, 2)
        Write-Host "    완료: $path ($sz MB)" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "    경고: $label 다운로드 실패 — $($_.Exception.Message)" -ForegroundColor DarkYellow
        Write-Host "    수동 다운로드: $url" -ForegroundColor DarkYellow
        Write-Host "    파일 위치: $path" -ForegroundColor DarkYellow
        return $false
    }
}

$vcRedistPath = Join-Path $Root 'installer\vc_redist.x64.exe'
Download-Once 'https://aka.ms/vs/17/release/vc_redist.x64.exe' $vcRedistPath '[0.5/3] VC++ 2015-2022' | Out-Null

# WebView2 Evergreen Bootstrapper — pywebview fallback 용.
# 클린 Windows (특히 LTSC / Server) 에서 WebView2 가 없으면 pywebview 가 실패하므로
# 인스톨러가 자동으로 같이 설치하도록 번들.
$wv2Path = Join-Path $Root 'installer\MicrosoftEdgeWebview2Setup.exe'
Download-Once 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' $wv2Path '[0.6/3] WebView2 Bootstrapper' | Out-Null

Write-Host ''

# --- [1/3] PyInstaller 로 exe 폴더 빌드 ---
Write-Host '[1/3] PyInstaller 실행 (build-exe.ps1)...' -ForegroundColor Yellow
& (Join-Path $Root 'build-exe.ps1')
if ($LASTEXITCODE -ne 0) { throw 'build-exe.ps1 failed' }

$exeDir = Join-Path $Root 'dist\DB-care'
if (-not (Test-Path (Join-Path $exeDir 'DB-care.exe'))) {
    throw "PyInstaller 출력 없음: $exeDir\DB-care.exe"
}

# --- [2/3] Inno Setup 컴파일 ---
Write-Host ''
Write-Host '[2/3] Inno Setup 컴파일...' -ForegroundColor Yellow
$iss = Join-Path $Root 'installer\DB-care.iss'
if (-not (Test-Path $iss)) {
    throw "Inno Setup 스크립트 없음: $iss"
}

& $ISCC $iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup 컴파일 실패' }

# --- [3/3] 결과 확인 ---
$setupExe = Join-Path $Root "dist\DB-care_Setup_v$Version.exe"
if (-not (Test-Path $setupExe)) {
    throw "설치 exe 생성 실패: $setupExe"
}

$sizeMB = [math]::Round((Get-Item $setupExe).Length / 1MB, 2)

Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host ' BUILD SUCCESS' -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
Write-Host ''
Write-Host "  설치 프로그램 : $setupExe"
Write-Host "  크기          : $sizeMB MB"
Write-Host ''
Write-Host '배포 방법:' -ForegroundColor Cyan
Write-Host '  1) 위 exe 파일을 USB / 네트워크 드라이브로 복사'
Write-Host '  2) 다른 원내 PC 에서 더블클릭 → 설치 마법사 시작'
Write-Host '  3) 설치 완료 후 바탕화면 / 시작메뉴에서 DB-care 실행'
Write-Host ''
Write-Host '참고:' -ForegroundColor DarkGray
Write-Host '  - Windows 10/11 64비트 필요'
Write-Host '  - 첫 실행 시 Edge WebView2 런타임 자동 감지'
Write-Host '  - 환자 DB 는 %APPDATA%\DB-care\ 에 저장 (재설치해도 유지)'
Write-Host ''
