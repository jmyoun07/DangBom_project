"""
파생 변수 자동 계산 (병원 원본값 → 40+ 모델 입력값).

병원이 `build_template.py` 양식으로 올린 원본값을 받아 파생 지표를
계산해 Patient 인스턴스에 채워 넣는다. 업로드 / PATCH / POST 모두
여기에서 단일 소스로 계산해 DB 에 저장.

v2.2 변경사항:
  - age : dob + exam_date 로부터 자동 계산 (병원 입력 불필요)
  - ldl : 병원 실측치가 있으면 그대로 사용 → 없을 때만 Friedewald 계산
  - HOMA_IR / HOMA_beta / BMI_HOMA_IR : c_peptide 기반으로 계산
    (v2.2 모델은 C_peptide 단위로 학습됨 — × 3.0 insulin 변환 불필요)
  - he_insulin : 하위호환용으로 c_peptide × 3.0 값을 저장 (구 UI/CSV 용)

저장 대상 (Patient 테이블 컬럼):
  age, bmi, ldl, he_insulin, dm_duration, egfr, ldl_calc, non_hdl,
  homa_ir, homa_beta, tyg_index, bmi_homa_ir, pulse_pressure
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


def _f(v: Any) -> float | None:
    """float 변환 — None/NaN/문자열 실패 시 None."""
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _to_date(v: Any) -> date | None:
    """str/date/datetime → date. 실패 시 None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    # ISO, slash, dot
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _age_from_dob(dob: date, on: date | None = None) -> int | None:
    """만 나이 계산. on 이 None 이면 오늘 기준."""
    if dob is None:
        return None
    ref = on or date.today()
    y = ref.year - dob.year
    if (ref.month, ref.day) < (dob.month, dob.day):
        y -= 1
    if 0 <= y <= 120:
        return y
    return None


def current_age(data: dict, on: date | None = None) -> int | None:
    """오늘(or on) 기준 만나이 — dob 우선, 없으면 저장 age fallback.

    v2.2.2 (H3): PatientDetail/List 표시 나이와 예측에 쓰는 나이를 동일 소스로 통일.
    저장된 age 컬럼은 검사일(exam_date) 시점 나이라 시간이 지나면 표시 나이와 어긋난다.
    """
    dob = _to_date(data.get("dob"))
    if dob is not None:
        a = _age_from_dob(dob, on)
        if a is not None:
            return a
    fa = _f(data.get("age"))
    return int(fa) if fa is not None else None


def current_dm_duration(data: dict, on: date | None = None) -> int | None:
    """현재 만나이 − 진단 시 나이. fallback: 저장 dm_duration."""
    age = current_age(data, on)
    diag = _f(data.get("dm_diagnosis_age"))
    if age is not None and diag is not None:
        d = age - int(diag)
        if 0 <= d <= 120:
            return d
    fd = _f(data.get("dm_duration"))
    return int(fd) if fd is not None else None


def _ckd_epi_egfr(cr: float, age: float, sex: str) -> float | None:
    """
    CKD-EPI 2009 공식. sex: 'M' / 'F' (대소문자 무관).
    반환: eGFR (mL/min/1.73m²), 계산 불가 시 None.
    """
    if cr is None or age is None or not sex:
        return None
    if cr <= 0 or age <= 0:
        return None
    is_male = str(sex).upper().startswith("M")
    kappa = 0.9 if is_male else 0.7
    alpha = -0.411 if is_male else -0.329
    factor_sex = 1.0 if is_male else 1.018
    ratio = cr / kappa
    try:
        val = 141.0 * (min(ratio, 1.0) ** alpha) * (max(ratio, 1.0) ** -1.209) \
              * (0.993 ** age) * factor_sex
        return round(val, 1)
    except Exception:
        return None


def compute_derived(data: dict) -> dict:
    """
    입력 dict 에 파생 변수를 계산해 **그대로 채워 반환** (in-place 아님).
    이미 값이 있는 키는 덮어쓰지 않는다 (병원이 실측치를 준 경우 존중).

    Args:
        data: Patient 필드명 dict (소문자 영문). 예: {'fbg': 140, 'hba1c': 7.2, ...}
    Returns:
        파생값이 채워진 새 dict.
    """
    out = dict(data)

    # ── 나이 자동 계산 (DOB → age) ─────────────────────────
    # 병원 양식은 dob 를 필수로 받고 age 는 입력하지 않음.
    dob = _to_date(out.get("dob"))
    exam_date = _to_date(out.get("exam_date"))
    if out.get("age") is None and dob is not None:
        calc_age = _age_from_dob(dob, exam_date)
        if calc_age is not None:
            out["age"] = calc_age

    age = _f(out.get("age"))
    sex = out.get("sex")
    weight = _f(out.get("weight"))
    height = _f(out.get("height"))
    chol = _f(out.get("total_cholesterol"))
    hdl = _f(out.get("hdl"))
    tg = _f(out.get("triglycerides"))
    fbg = _f(out.get("fbg"))
    c_peptide = _f(out.get("c_peptide"))
    he_insulin = _f(out.get("he_insulin"))
    bmi = _f(out.get("bmi"))
    sbp = _f(out.get("sbp"))
    dbp = _f(out.get("dbp"))
    cr = _f(out.get("cr"))
    dm_diag = _f(out.get("dm_diagnosis_age"))
    ldl_input = _f(out.get("ldl"))   # 병원 실측치 우선

    # BMI (키/몸무게로)
    if out.get("bmi") is None and height and weight and height > 0:
        bmi = round(weight / ((height / 100.0) ** 2), 1)
        out["bmi"] = bmi

    # LDL
    #   1순위: 병원 실측치 (ldl_input) — 이미 out["ldl"] 에 있음
    #   2순위: Friedewald 계산 (TG < 400 에서만 신뢰)
    ldl_calc = None
    if chol is not None and hdl is not None and tg is not None and tg < 400:
        _ldl = round(chol - hdl - tg / 5.0, 1)
        # v2.2.2 (M8): 음수 LDL = HDL>총콜레스테롤 등 비정상 입력 → 계산 불가로 처리.
        #   음수값이 "정상 LDL" 처럼 표시되는 의료 오해를 막는다.
        ldl_calc = _ldl if _ldl >= 0 else None
    if out.get("ldl") is None and ldl_calc is not None:
        out["ldl"] = ldl_calc
    # ldl_calc 컬럼은 항상 계산값 저장 (모델 입력용 — 참조 지표)
    if ldl_calc is not None:
        out["ldl_calc"] = ldl_calc
    elif ldl_input is not None:
        # Friedewald 계산 불가 시 병원 LDL 실측치를 ldl_calc 로도 채움
        out["ldl_calc"] = ldl_input

    # non-HDL
    if chol is not None and hdl is not None:
        _nonhdl = round(chol - hdl, 1)
        if _nonhdl >= 0:  # v2.2.2 (M8): HDL>총콜레스테롤 비정상 입력 시 음수 방지
            out["non_hdl"] = _nonhdl

    # HE_insulin 추정 (c_peptide × 3.0) — 하위호환용 저장
    # 모델 v2.2 는 c_peptide 를 직접 사용하지만 기존 UI/CSV 가 he_insulin 필드를
    # 참조할 수 있어 함께 저장.
    if out.get("he_insulin") is None and c_peptide is not None:
        he_insulin = round(c_peptide * 3.0, 2)
        out["he_insulin"] = he_insulin
    # 역방향: c_peptide 가 없고 he_insulin 만 있으면 c_peptide 역추정 (구 데이터 호환)
    if c_peptide is None and he_insulin is not None:
        c_peptide = round(he_insulin / 3.0, 2)

    # HOMA 지수 — v2.2 C-peptide 기반
    if fbg is not None and c_peptide is not None and fbg > 0:
        out["homa_ir"] = round(fbg * c_peptide / 405.0, 3)
        if fbg > 63:
            out["homa_beta"] = round(360.0 * c_peptide / (fbg - 63.0), 2)

    # TyG index = ln(TG × glu / 2)
    if tg is not None and fbg is not None and tg > 0 and fbg > 0:
        try:
            out["tyg_index"] = round(math.log(tg * fbg / 2.0), 3)
        except Exception:
            pass

    # BMI × HOMA_IR
    if bmi is not None and out.get("homa_ir") is not None:
        out["bmi_homa_ir"] = round(bmi * out["homa_ir"], 3)

    # Pulse pressure — v2.2.2 (M8): SBP < DBP 비정상 입력이면 음수 맥압 대신 미산출.
    if sbp is not None and dbp is not None and sbp >= dbp:
        out["pulse_pressure"] = round(sbp - dbp, 1)

    # Hypertension (한국 고혈압학회 기준: SBP ≥ 140 OR DBP ≥ 90)
    # 병원은 별도 진단 여부를 수집하지 않으므로 혈압값에서 자동 파생.
    # 단, 병원이 명시적으로 hypertension 값을 넣어줬다면 그 값을 존중.
    if out.get("hypertension") is None and sbp is not None and dbp is not None:
        out["hypertension"] = 1 if (sbp >= 140 or dbp >= 90) else 0

    # eGFR (CKD-EPI)
    if cr is not None and age is not None and sex:
        egfr = _ckd_epi_egfr(cr, age, sex)
        if egfr is not None:
            out["egfr"] = egfr

    # DM duration
    if out.get("dm_duration") is None and age is not None and dm_diag is not None:
        try:
            dur = int(age) - int(dm_diag)
            if 0 <= dur <= 120:
                out["dm_duration"] = dur
        except Exception:
            pass

    return out
