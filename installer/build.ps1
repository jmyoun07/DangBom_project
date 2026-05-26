# ==================================================
#  DB-care Release Builder (Windows PowerShell)
#  프론트엔드 빌드 + 백엔드 복사 + 실행 스크립트 → zip
# ==================================================

$ErrorActionPreference = 'Stop'

# Paths
$Root       = Split-Path -Parent $PSScriptRoot
$Installer  = Join-Path $Root 'installer'
$Frontend   = Join-Path $Root 'frontend'
$Backend    = Join-Path $Root 'backend'
$Template   = Join-Path $Installer 'template'
$DistRoot   = Join-Path $Root 'dist'
$BuildRoot  = Join-Path $Installer 'build'
$Stage      = Join-Path $BuildRoot 'DB-care'

# Version
$Version = '1.0.0'
$ZipName = "DB-care-v$Version.zip"
$ZipPath = Join-Path $DistRoot $ZipName

Write-Host ''
Write-Host '======================================' -ForegroundColor Cyan
Write-Host " DB-care Release Builder v$Version" -ForegroundColor Cyan
Write-Host '======================================' -ForegroundColor Cyan
Write-Host ''

# [1/5] Clean
Write-Host '[1/5] 이전 빌드 정리...'
if (Test-Path $BuildRoot) { Remove-Item -Recurse -Force $BuildRoot }
New-Item -ItemType Directory -Path $Stage | Out-Null
if (-not (Test-Path $DistRoot)) { New-Item -ItemType Directory -Path $DistRoot | Out-Null }

# [2/5] Frontend build
Write-Host '[2/5] 프론트엔드 빌드 (npm run build)...'
Push-Location $Frontend
try {
    if (-not (Test-Path 'node_modules')) {
        Write-Host '    node_modules 없음 → npm install 실행'
        npm install
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build 실패" }
} finally {
    Pop-Location
}

# [3/5] Stage backend + built frontend
Write-Host '[3/5] 패키징 (백엔드 + 빌드된 프론트엔드)...'

# Backend (exclude __pycache__, venv, *.db)
$BackendStage = Join-Path $Stage 'backend'
New-Item -ItemType Directory -Path $BackendStage | Out-Null
Get-ChildItem -Path $Backend -Force | Where-Object {
    $_.Name -notin @('__pycache__', 'venv', '.venv', 'node_modules') -and
    $_.Name -notmatch '\.db$' -and
    $_.Name -notmatch '\.pyc$'
} | ForEach-Object {
    $src  = $_.FullName
    $dest = Join-Path $BackendStage $_.Name
    if ($_.PSIsContainer) {
        Copy-Item -Recurse -Force $src $dest
        # Clean nested __pycache__
        Get-ChildItem -Path $dest -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force
    } else {
        Copy-Item -Force $src $dest
    }
}

# Frontend dist → stage/frontend_dist
$DistSrc = Join-Path $Frontend 'dist'
if (-not (Test-Path $DistSrc)) {
    throw "frontend/dist 폴더가 없습니다. 프론트엔드 빌드가 실패했을 수 있습니다."
}
$FrontendStage = Join-Path $Stage 'frontend_dist'
Copy-Item -Recurse -Force $DistSrc $FrontendStage

# Template files (start/install/README)
Write-Host '[4/5] 실행 스크립트 복사...'
Get-ChildItem -Path $Template -File | ForEach-Object {
    Copy-Item -Force $_.FullName (Join-Path $Stage $_.Name)
}

# Write VERSION file
Set-Content -Path (Join-Path $Stage 'VERSION.txt') -Value @"
DB-care v$Version
Build date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
"@

# [5/5] Zip
Write-Host '[5/5] zip 압축...'
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $Stage -DestinationPath $ZipPath -CompressionLevel Optimal

# Report
$SizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host ''
Write-Host '======================================' -ForegroundColor Green
Write-Host ' 빌드 완료!' -ForegroundColor Green
Write-Host ''
Write-Host " 파일 : $ZipPath"
Write-Host " 크기 : $SizeMB MB"
Write-Host '======================================' -ForegroundColor Green
Write-Host ''
