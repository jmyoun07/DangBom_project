# ==========================================================
#  DB-care Desktop EXE Builder
#  Frontend build -> bundle backend + frontend dist + launcher
#  Output: dist/DB-care/DB-care.exe
# ==========================================================

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot

Write-Host ''
Write-Host '==========================================' -ForegroundColor Cyan
Write-Host ' DB-care Desktop EXE Builder' -ForegroundColor Cyan
Write-Host '==========================================' -ForegroundColor Cyan
Write-Host ''

# --- [1/5] Prerequisites ---
Write-Host '[1/5] Checking tools...' -ForegroundColor Yellow

$pyVer = (python --version 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Python not found. Install Python 3.11+ first."
}
Write-Host "    $pyVer"

$nodeVer = (node --version 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Node.js not found."
}
Write-Host "    node $nodeVer"

# --- [2/5] Desktop deps ---
Write-Host ''
Write-Host '[2/5] Installing desktop deps (pywebview, pyinstaller)...' -ForegroundColor Yellow
python -m pip install --disable-pip-version-check -q -r (Join-Path $Root 'requirements-desktop.txt')
python -m pip install --disable-pip-version-check -q -r (Join-Path $Root 'backend\requirements.txt')

# --- [3/5] Frontend build ---
Write-Host ''
Write-Host '[3/5] Building frontend (npm run build)...' -ForegroundColor Yellow
Push-Location (Join-Path $Root 'frontend')
try {
    if (-not (Test-Path 'node_modules')) {
        Write-Host '    node_modules missing -> npm install'
        npm install
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
} finally {
    Pop-Location
}

# --- [4/5] Clean previous output ---
Write-Host ''
Write-Host '[4/5] Cleaning previous builds...' -ForegroundColor Yellow
$distDir  = Join-Path $Root 'dist'
$buildDir = Join-Path $Root 'build'
$specFile = Join-Path $Root 'DB-care.spec'
if (Test-Path $distDir)  { Remove-Item -Recurse -Force $distDir }
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
if (Test-Path $specFile) { Remove-Item -Force $specFile }

# --- [5/5] PyInstaller ---
Write-Host ''
Write-Host '[5/5] Running PyInstaller... (takes 5-10 min)' -ForegroundColor Yellow

$iconArg = @()
$iconPath = Join-Path $Root 'installer\db-care.ico'
if (Test-Path $iconPath) {
    $iconArg = @('--icon', $iconPath)
    Write-Host "    icon: $iconPath"
} else {
    Write-Host "    No custom icon. Put installer\db-care.ico to use one."
}

# 버전/게시자 메타데이터 — SmartScreen 경고에 회사명 노출 (서명은 별도)
$versionArg = @()
$versionPath = Join-Path $Root 'installer\version_info.txt'
if (Test-Path $versionPath) {
    $versionArg = @('--version-file', $versionPath)
    Write-Host "    version-info: $versionPath"
}

$pyiArgs = @(
    '--noconfirm',
    '--clean',
    '--onedir',
    '--windowed',
    '--name', 'DB-care',
    '--add-data', "backend$([IO.Path]::PathSeparator)backend",
    '--add-data', "frontend\dist$([IO.Path]::PathSeparator)frontend_dist",

    # --- ML / 데이터 스택 ---
    '--collect-all', 'sklearn',
    '--collect-all', 'xgboost',
    '--collect-all', 'imblearn',
    '--collect-all', 'pandas',
    '--collect-all', 'numpy',
    '--collect-all', 'joblib',
    '--collect-all', 'scipy',
    '--collect-all', 'threadpoolctl',

    # --- FastAPI / Pydantic / Starlette 생태계 ---
    # launcher.py 에서 함수 내부 동적 import + sys.path 조작 때문에
    # PyInstaller 정적 분석기가 fastapi 등을 자동 발견 못함 → 강제 collect.
    '--collect-all', 'fastapi',
    '--collect-all', 'starlette',
    '--collect-all', 'pydantic',
    '--collect-all', 'pydantic_core',
    '--collect-all', 'sqlalchemy',
    '--collect-all', 'uvicorn',
    '--collect-all', 'anyio',
    '--collect-all', 'sniffio',
    '--collect-all', 'h11',
    '--collect-all', 'click',
    '--collect-all', 'typing_extensions',
    '--collect-all', 'annotated_types',
    '--collect-all', 'idna',
    '--collect-all', 'certifi',
    '--hidden-import', 'multipart',
    '--hidden-import', 'python_multipart',
    '--hidden-import', 'dotenv',
    '--hidden-import', 'email_validator',

    # --- 백엔드 자체 모듈 (sys.path = backend/ 아래) ---
    # PyInstaller 가 launcher 의 동적 sys.path.insert 를 못 따라가므로
    # backend/ 를 별도 검색경로로 명시 + 진입점들을 hidden-import 로 강제.
    '--paths', 'backend',
    '--hidden-import', 'main',
    '--hidden-import', 'models',
    '--hidden-import', 'models.database',
    '--hidden-import', 'models.schemas',
    '--hidden-import', 'routers',
    '--hidden-import', 'routers.patients',
    '--hidden-import', 'routers.prediction',
    '--hidden-import', 'routers.scenario',
    '--hidden-import', 'routers.case_comparison',
    '--hidden-import', 'routers.upload',
    '--hidden-import', 'ml',
    '--hidden-import', 'ml.predictor',
    '--hidden-import', 'services',
    '--hidden-import', 'services.derived',

    # --- 기타 ---
    '--hidden-import', 'email.mime.multipart',
    '--hidden-import', 'email.mime.text',
    '--hidden-import', 'pywebview',
    '--hidden-import', 'webview.platforms.edgechromium',
    '--hidden-import', 'webview.platforms.mshtml',
    # --- DB-care 는 torch/transformers 등 LLM 스택을 쓰지 않는다.
    # 시스템 Python 에 설치돼 있으면 PyInstaller 가 자동 스캔하다가
    # torch DLL 로딩 중 Windows access violation 으로 멈춘다 → 전부 제외.
    '--exclude-module', 'torch',
    '--exclude-module', 'torchvision',
    '--exclude-module', 'torchaudio',
    '--exclude-module', 'transformers',
    '--exclude-module', 'tensorflow',
    '--exclude-module', 'tensorboard',
    '--exclude-module', 'keras',
    '--exclude-module', 'jax',
    '--exclude-module', 'jaxlib',
    '--exclude-module', 'flax',
    '--exclude-module', 'datasets',
    '--exclude-module', 'tokenizers',
    '--exclude-module', 'sentencepiece',
    '--exclude-module', 'accelerate',
    '--exclude-module', 'safetensors',
    '--exclude-module', 'triton',
    '--exclude-module', 'onnx',
    '--exclude-module', 'onnxruntime',
    '--exclude-module', 'cv2',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'seaborn',
    '--exclude-module', 'plotly',
    '--exclude-module', 'IPython',
    '--exclude-module', 'jupyter',
    '--exclude-module', 'notebook',
    '--exclude-module', 'ipykernel',
    '--exclude-module', 'ipywidgets',
    '--exclude-module', 'pytest',
    '--exclude-module', 'sphinx'
)
$pyiArgs += $iconArg
$pyiArgs += $versionArg
$pyiArgs += 'launcher.py'

python -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# --- Report ---
$exePath = Join-Path $distDir 'DB-care\DB-care.exe'
if (-not (Test-Path $exePath)) {
    throw "Build finished but $exePath not found."
}

$sizeMB = [math]::Round((Get-ChildItem -Recurse (Split-Path $exePath) | Measure-Object -Property Length -Sum).Sum / 1MB, 2)

Write-Host ''
Write-Host '==========================================' -ForegroundColor Green
Write-Host ' BUILD SUCCESS' -ForegroundColor Green
Write-Host '==========================================' -ForegroundColor Green
Write-Host ''
Write-Host "  exe  : $exePath"
Write-Host "  size : $sizeMB MB"
Write-Host ''
Write-Host '  Test    : double-click the exe above'
Write-Host '  Deploy  : copy the whole dist\DB-care\ folder,'
Write-Host '            or use Inno Setup to make an installer.'
Write-Host ''
