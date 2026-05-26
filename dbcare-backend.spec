# -*- mode: python ; coding: utf-8 -*-
#
# DB-care Backend Sidecar Spec — Tauri 마이그용.
# entry: backend_entry.py → dist\dbcare-backend\dbcare-backend.exe (+ _internal/)
# Tauri build 가 dist\dbcare-backend\ 폴더 통째를 resources 로 번들.
#
# 기존 DB-care.spec 와 다른 점:
#   - entry 가 launcher.py → backend_entry.py (Edge 실행 / pywebview / 단일 인스턴스 락 제거)
#   - datas 에서 frontend\dist 제거 (Tauri 가 frontendDist 로 직접 처리)
#   - hiddenimports 에서 pywebview / webview.platforms.* 제거
#   - name 변경 — DB-care → dbcare-backend
from PyInstaller.utils.hooks import collect_all

datas = [('backend', 'backend')]
binaries = []
hiddenimports = [
    'multipart', 'python_multipart', 'dotenv', 'email_validator',
    'main',
    'models', 'models.database', 'models.schemas',
    'routers', 'routers.patients', 'routers.prediction', 'routers.scenario',
    'routers.case_comparison', 'routers.upload',
    'ml', 'ml.predictor',
    'services', 'services.derived',
    'email.mime.multipart', 'email.mime.text',
]

for pkg in [
    'sklearn', 'xgboost', 'imblearn', 'pandas', 'numpy', 'joblib', 'scipy',
    'threadpoolctl', 'fastapi', 'starlette', 'pydantic', 'pydantic_core',
    'sqlalchemy', 'uvicorn', 'anyio', 'sniffio', 'h11', 'click',
    'typing_extensions', 'annotated_types', 'idna', 'certifi',
]:
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]


a = Analysis(
    ['backend_entry.py'],
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchvision', 'torchaudio', 'transformers', 'tensorflow',
        'tensorboard', 'keras', 'jax', 'jaxlib', 'flax', 'datasets',
        'tokenizers', 'sentencepiece', 'accelerate', 'safetensors', 'triton',
        'onnx', 'onnxruntime', 'cv2', 'matplotlib', 'seaborn', 'plotly',
        'IPython', 'jupyter', 'notebook', 'ipykernel', 'ipywidgets',
        'pytest', 'sphinx',
        # Tauri 가 UI 담당 — pywebview / webbrowser 불필요
        'pywebview', 'webview',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='dbcare-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='installer/version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='dbcare-backend',
)
