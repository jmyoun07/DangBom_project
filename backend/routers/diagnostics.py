"""
DB-care 자가 진단 + 데이터 폴더 관리 API.

엔드포인트:
  GET  /api/v1/diagnostics       — 환경/DB/ML 모델 상태 점검 결과
  GET  /api/v1/export/folder     — CSV 미러 폴더 경로 반환 (프론트에서 "폴더 열기" 용)
  POST /api/v1/export/refresh    — 전체 환자 CSV 일괄 재미러 (수동 트리거)
  POST /api/v1/export/open       — 탐색기로 폴더 열기 (데스크탑 환경에서만 동작)
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import Patient, MeasurementHistory, get_db, DB_FILE
from services.export_csv import export_all_patients, get_export_root
from ml.predictor import _load_model

router = APIRouter(prefix="/api/v1", tags=["diagnostics"])


# ── /api/v1/diagnostics ─────────────────────────────────────

def _disk_free_gb(path: Path) -> float | None:
    try:
        total, used, free = shutil.disk_usage(str(path))
        return round(free / (1024 ** 3), 2)
    except Exception:
        return None


def _check_ml_model(name: str) -> dict:
    """pkl 파일 존재 + 로드 성공 여부."""
    try:
        pkg = _load_model(name)
        if pkg is None:
            return {"available": False, "reason": "pkl 파일 없음 또는 로드 실패"}
        feats = pkg.get("features", []) if isinstance(pkg, dict) else []
        return {
            "available": True,
            "n_features": len(feats),
            "model_type": pkg.get("model_type") if isinstance(pkg, dict) else "?",
        }
    except Exception as e:
        return {"available": False, "reason": str(e)[:200]}


@router.get("/diagnostics")
def diagnostics(db: Session = Depends(get_db)):
    """프론트 Settings 페이지의 '환경 점검' 버튼이 호출.
    프로그램이 정상 작동하는 데 필요한 요소가 모두 있는지 점검."""
    db_path = Path(DB_FILE)
    export_path = get_export_root()

    # 환자/측정 통계
    n_patients = db.query(Patient).count()
    n_meas = db.query(MeasurementHistory).count()

    # ML 모델 3개 상태
    ml_status = {
        "retinopathy":    _check_ml_model("retinopathy"),
        "kidney_disease": _check_ml_model("kidney_disease"),
        "cardiovascular": _check_ml_model("cardiovascular"),
    }

    # 전체 정상 여부 — 핵심 체크리스트 모두 OK 면 ready=True
    checks = {
        "database_file":   db_path.exists(),
        "export_folder":   export_path.exists(),
        "ml_retinopathy":  ml_status["retinopathy"]["available"],
        "ml_kidney":       ml_status["kidney_disease"]["available"],
        "ml_cardio":       ml_status["cardiovascular"]["available"],
    }
    all_ok = all(checks.values())

    return {
        "data": {
            "ready": all_ok,
            "checks": checks,
            "environment": {
                "platform": platform.platform(),
                "python_version": sys.version.split()[0],
                "frozen": getattr(sys, "frozen", False),
            },
            "storage": {
                "database_path": str(db_path),
                "database_exists": db_path.exists(),
                "database_size_mb": round(db_path.stat().st_size / (1024 ** 2), 2) if db_path.exists() else 0,
                "export_path": str(export_path),
                "disk_free_gb": _disk_free_gb(db_path.parent),
            },
            "data_counts": {
                "patients": n_patients,
                "measurements": n_meas,
            },
            "ml_models": ml_status,
        },
        "success": True,
    }


# ── /api/v1/export/* ─────────────────────────────────────────

@router.get("/export/folder")
def get_export_folder():
    """프론트가 폴더 경로를 안내 / 열기에 사용."""
    p = get_export_root()
    return {"data": {"path": str(p), "exists": p.exists()}, "success": True}


@router.post("/export/refresh")
def refresh_export(db: Session = Depends(get_db)):
    """모든 환자 CSV 미러를 즉시 일괄 재생성."""
    result = export_all_patients(db)
    return {"data": result, "success": True}


@router.post("/export/open")
def open_export_folder():
    """
    OS 파일 탐색기로 CSV 미러 폴더 열기.
    데스크탑 환경에서만 동작 — DBCARE_DESKTOP=1 또는 frozen 빌드.
    """
    p = get_export_root()
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)

    is_desktop = getattr(sys, "frozen", False) or os.environ.get("DBCARE_DESKTOP") == "1"
    if not is_desktop:
        # 개발 모드에선 경로만 반환 (서버 PC 의 탐색기 열어주면 곤란)
        return {"data": {"opened": False, "path": str(p), "reason": "desktop mode only"}, "success": True}

    try:
        if sys.platform == "win32":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"data": {"opened": True, "path": str(p)}, "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"폴더 열기 실패: {e}")
