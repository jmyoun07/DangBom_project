"""
Pydantic Schemas for API request/response
"""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel
from typing import Optional


# ── Patient ───────────────────────────────────────────────────

class PatientBase(BaseModel):
    """v2 스키마 — 병원 수집 변수 기준 (KNHANES 매칭)."""
    # ── 메타데이터 ──────────────────────────────
    name: str
    chart_no: str
    dob: Optional[date] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    exam_date: Optional[date] = None

    # ── 혈당·인슐린 ─────────────────────────────
    hba1c: Optional[float] = None           # HE_HbA1c
    c_peptide: Optional[float] = None       # 병원 실측. he_insulin 자동 변환
    fbg: Optional[float] = None             # HE_glu
    he_insulin: Optional[float] = None      # (선택) 실측 가능 시만

    # ── 간효소 ──────────────────────────────────
    ggt: Optional[float] = None             # 참고용 (모델 미사용)
    alt: Optional[float] = None
    ast: Optional[float] = None

    # ── 신장 ────────────────────────────────────
    cr: Optional[float] = None              # HE_crea (→ eGFR 파생)

    # ── 지질 ────────────────────────────────────
    total_cholesterol: Optional[float] = None
    triglycerides: Optional[float] = None
    hdl: Optional[float] = None
    ldl: Optional[float] = None             # 실측 LDL (없으면 LDL_calc 파생)

    # ── 혈압·신체 ──────────────────────────────
    sbp: Optional[float] = None
    dbp: Optional[float] = None
    bmi: Optional[float] = None
    height: Optional[float] = None          # HE_ht
    weight: Optional[float] = None          # HE_wt

    # ── 소변 dipstick (기본 3 + 확장 6) ────────
    he_upro: Optional[float] = None
    he_uglu: Optional[float] = None
    he_ubld: Optional[float] = None
    urine_bil: Optional[float] = None
    urine_uro: Optional[float] = None
    urine_ket: Optional[float] = None
    urine_nit: Optional[int] = None
    urine_ph: Optional[float] = None
    urine_sg: Optional[float] = None

    # ── 과거력·당뇨 ────────────────────────────
    hypertension: Optional[int] = 0
    dm_diagnosis_age: Optional[int] = None
    dm_duration: Optional[int] = None
    dm_medication: Optional[int] = 0
    insulin_medication: Optional[int] = 0

    # ── 생활습관 ────────────────────────────────
    smoking: Optional[int] = 0
    drinking: Optional[int] = 0
    exercise: Optional[int] = 0
    sleep_hours: Optional[float] = None

    # ── 기타 (참고용) ──────────────────────────
    visceral_fat: Optional[float] = None

    # ── 백엔드 자동 파생 변수 (compute_derived) ──
    # API 응답에 포함되어야 PatientDetail / Dashboard 가 eGFR·HOMA·LDL_calc 표시 가능.
    egfr: Optional[float] = None
    ldl_calc: Optional[float] = None
    non_hdl: Optional[float] = None
    homa_ir: Optional[float] = None
    homa_beta: Optional[float] = None
    tyg_index: Optional[float] = None
    bmi_homa_ir: Optional[float] = None
    pulse_pressure: Optional[float] = None


class PatientCreate(PatientBase):
    pass


class PatientUpdate(PatientBase):
    """환자 정보 수정용 — 모든 필드 optional"""
    name: Optional[str] = None
    chart_no: Optional[str] = None


class PatientResponse(PatientBase):
    id: int
    upload_date: Optional[datetime] = None
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True


class PatientListResponse(BaseModel):
    data: list[PatientResponse]
    total: int
    page: int
    size: int
    success: bool = True


# ── Measurement History ───────────────────────────────────────

class MeasurementResponse(BaseModel):
    id: int
    patient_id: int
    measured_at: date
    c_peptide: Optional[float] = None
    hba1c: Optional[float] = None
    cr: Optional[float] = None

    class Config:
        from_attributes = True


# ── Prediction ────────────────────────────────────────────────

class PredictRequest(BaseModel):
    patient_id: int


class SimulateRequest(BaseModel):
    patient_id: int
    c_peptide: float
    hba1c: float


class ScenarioRequest(BaseModel):
    patient_id: int
    c_peptide: float
    hba1c: float
