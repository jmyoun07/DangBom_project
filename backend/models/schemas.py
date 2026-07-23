"""
Pydantic Schemas for API request/response
"""
from __future__ import annotations
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from services.derived import normalize_sex


# ── Patient ───────────────────────────────────────────────────
# v2.1.9 (감사): 의료 수치 범위 검증 추가. 범위는 "생리적으로 가능한 극단"까지
# 느슨하게 잡아 실데이터 거부를 피하되, 명백한 오입력(음수/단위실수)은 차단.

class PatientBase(BaseModel):
    """v2 스키마 — 병원 수집 변수 기준 (KNHANES 매칭)."""
    # ── 메타데이터 ──────────────────────────────
    name: str = Field(..., min_length=1, max_length=100)
    chart_no: str = Field(..., min_length=1, max_length=50)
    dob: Optional[date] = None
    sex: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=120)
    phone: Optional[str] = Field(None, max_length=30)
    exam_date: Optional[date] = None

    # ── 혈당·인슐린 ─────────────────────────────
    hba1c: Optional[float] = Field(None, ge=2.0, le=25.0)        # HE_HbA1c (%)
    c_peptide: Optional[float] = Field(None, ge=0.0, le=50.0)    # ng/mL
    fbg: Optional[float] = Field(None, ge=10.0, le=1500.0)       # HE_glu mg/dL (극단 고혈당 수용)
    he_insulin: Optional[float] = Field(None, ge=0.0, le=300.0)

    # ── 간효소 ──────────────────────────────────
    ggt: Optional[float] = Field(None, ge=0.0, le=2000.0)
    alt: Optional[float] = Field(None, ge=0.0, le=2000.0)
    ast: Optional[float] = Field(None, ge=0.0, le=2000.0)

    # ── 신장 ────────────────────────────────────
    cr: Optional[float] = Field(None, ge=0.0, le=30.0)          # HE_crea (→ eGFR 파생)

    # ── 지질 ────────────────────────────────────
    total_cholesterol: Optional[float] = Field(None, ge=0.0, le=1000.0)
    triglycerides: Optional[float] = Field(None, ge=0.0, le=10000.0)  # 극단 고중성지방혈증 수용
    hdl: Optional[float] = Field(None, ge=0.0, le=300.0)
    ldl: Optional[float] = Field(None, ge=0.0, le=1000.0)       # 실측 LDL (없으면 LDL_calc 파생)

    # ── 혈압·신체 ──────────────────────────────
    sbp: Optional[float] = Field(None, ge=40.0, le=320.0)
    dbp: Optional[float] = Field(None, ge=20.0, le=220.0)
    bmi: Optional[float] = Field(None, ge=8.0, le=90.0)
    height: Optional[float] = Field(None, ge=80.0, le=230.0)    # HE_ht cm
    weight: Optional[float] = Field(None, ge=15.0, le=350.0)    # HE_wt kg

    @field_validator("sex")
    @classmethod
    def _validate_sex(cls, v):
        # v2.2.6 (감사 H1): 업로드·모델·eGFR 과 동일한 normalize_sex 단일 소스 사용.
        #   ('남자'/'여자'/'1.0'/'2.0'/'male'/'female' 등도 일관 처리)
        if v is None:
            return v
        ns = normalize_sex(v)
        if ns is None:
            raise ValueError("sex must be M/F (or 1/2, 남/여)")
        return ns

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
    # v2.3.0 (감사): 미입력을 0('없음')으로 단정하지 않고 None(미상)으로 둔다.
    #   모델은 NaN → 학습된 KNNImputer 로 처리(train/serve 결측처리 일치).
    #   hypertension 은 혈압값이 있으면 compute_derived 가 자동 파생한다.
    hypertension: Optional[int] = None
    dm_diagnosis_age: Optional[int] = None
    dm_duration: Optional[int] = None
    dm_medication: Optional[int] = None
    insulin_medication: Optional[int] = None

    # ── 생활습관 ────────────────────────────────
    smoking: Optional[int] = None
    drinking: Optional[int] = None
    exercise: Optional[int] = None
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
    # v2.2.5: 조회 응답은 관대하게 — 이름/차트번호가 비어 있는 불완전 행도 "Field required"(422)로
    #   목록·상세가 통째로 깨지지 않게 Optional 로 완화. (생성 검증은 PatientCreate 에서 계속 강제)
    name: Optional[str] = None
    chart_no: Optional[str] = None
    upload_date: Optional[datetime] = None
    risk_level: Optional[str] = None

    # v2.2.8: 응답 스키마는 입력용 생리범위 제약(ge/le)을 상속하면 안 된다.
    #   DB 에 저장된 레거시/엣지 값(예 hba1c=0.0, fbg<10, sbp<40)에서 model_validate 가
    #   ValidationError 를 던져 목록/상세/by-chart/PATCH 응답이 통째로 500 으로 깨졌다.
    #   → 조회는 저장된 값을 그대로 통과시키고, 범위 검증은 입력(PatientCreate/Update)에서만.
    # v2.2.9: phone(max_length)·sex(_validate_sex) 제약도 해제 — 레거시 값('남성'/'U'/36자 phone)
    #   이 저장돼 있으면 목록 전체가 500 되던 문제 봉쇄. (업로드는 Pydantic 우회로 이런 값 저장 가능)
    phone: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    hba1c: Optional[float] = None
    c_peptide: Optional[float] = None
    fbg: Optional[float] = None
    he_insulin: Optional[float] = None
    ggt: Optional[float] = None
    alt: Optional[float] = None
    ast: Optional[float] = None
    cr: Optional[float] = None
    total_cholesterol: Optional[float] = None
    triglycerides: Optional[float] = None
    hdl: Optional[float] = None
    ldl: Optional[float] = None
    sbp: Optional[float] = None
    dbp: Optional[float] = None
    bmi: Optional[float] = None
    height: Optional[float] = None
    weight: Optional[float] = None

    @field_validator("sex")
    @classmethod
    def _validate_sex(cls, v):  # v2.2.9: 부모 검증 override — 조회는 저장값 그대로(비정상 sex도 500 금지)
        return v

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
    bmi: Optional[float] = None

    class Config:
        from_attributes = True


# ── Prediction ────────────────────────────────────────────────

class PredictRequest(BaseModel):
    patient_id: int


class SimulateRequest(BaseModel):
    patient_id: int
    c_peptide: float = Field(..., ge=0.0, le=50.0)
    hba1c: float = Field(..., ge=2.0, le=25.0)


class ScenarioRequest(BaseModel):
    patient_id: int
    c_peptide: float = Field(..., ge=0.0, le=50.0)
    hba1c: float = Field(..., ge=2.0, le=25.0)
