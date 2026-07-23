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

import json
import math
import re
from datetime import date, datetime
from typing import Any

# 저장 가능한 원본 임상 수치의 허용 범위.
# v2.3.2 (병원 피드백 — "데이터는 다 받아야"): 범위를 '명백한 입력오류(자릿수 실수·전사 오류)만
#   거른다' 수준으로 넓혔다. 경계값(HbA1c 2.9, LDL 5~8[병원 데이터가 mmol/L일 가능성] 등)은
#   버리지 않고 그대로 저장한다. 진짜 이상치(c_peptide 144·284 ng/mL 등 자릿수 오류)만 걸러 경고.
#   → 상한/하한은 '단위가 달라도(mg/dL↔mmol/L) 담기되, 오타/자릿수 실수는 잡히는' 넓은 폭.
# ⚠️ 이 범위는 models/schemas.py 의 PatientBase Field(ge/le) 제약과 **반드시 동일**해야 한다.
#   업로드(CSV)는 이 dict 로, 수기 POST/PATCH 는 Pydantic 으로 검증하므로 값이 어긋나면
#   같은 값이 한 경로에서만 거부되는 불일치가 생긴다. (codex 검토 M5 — 2026-07 동기화)
CLINICAL_RANGES: dict[str, tuple[float, float]] = {
    "hba1c": (2.0, 25.0),          # 2.9 저장(경계 저혈색소). 144·2.9오타 등은 범위로 처리
    "c_peptide": (0.01, 50.0),     # 144·284 = 자릿수 오류 → 거름. 0.0 = 실측 불가값 → 미측정 취급
    "he_insulin": (0.0, 300.0),    # c_peptide×3 하위호환 저장값 (schema 동기화)
    "cr": (0.0, 30.0),
    "bmi": (8.0, 90.0),
    "fbg": (10.0, 1500.0),
    "sbp": (40.0, 320.0),
    "dbp": (20.0, 220.0),
    "total_cholesterol": (0.0, 1000.0),
    "triglycerides": (0.0, 10000.0),
    "hdl": (0.0, 300.0),
    "ldl": (0.0, 1000.0),          # LDL 5~8(mg/dL 기준 낮음)도 저장. 자릿수오류(4자리)만 거름
    "ldl_calc": (0.0, 1000.0),     # Friedewald/실측 fallback도 LDL과 같은 저장 범위
    "alt": (0.0, 2000.0),
    "ast": (0.0, 2000.0),
    "ggt": (0.0, 2000.0),
    # v2.3.0 (감사): 음수 나이·키·몸무게 등 명백한 오입력 차단(파생값·모델 오염 방지).
    "age": (0.0, 120.0),
    "height": (80.0, 230.0),       # 성인 환자군 — 하한 80(비현실 BMI 폭주 방지, schema 동기화)
    "weight": (15.0, 350.0),
    "sleep_hours": (0.0, 24.0),
    "dm_diagnosis_age": (0.0, 120.0),
    # 이진 플래그 (0/1) — 범위 밖 값은 결측 처리 (임의 해석 금지)
    "dm_medication": (0.0, 1.0),
    "insulin_medication": (0.0, 1.0),
    "hypertension": (0.0, 1.0),
    "smoking": (0.0, 1.0),
    "drinking": (0.0, 1.0),
    "exercise": (0.0, 1.0),
    "urine_nit": (0.0, 1.0),
}

# 정확히 0 또는 1 만 허용하는 이진 플래그 (0.5 같은 중간값 거부)
BINARY_FIELDS: frozenset[str] = frozenset(
    {
        "dm_medication", "insulin_medication", "hypertension",
        "smoking", "drinking", "exercise", "urine_nit",
    }
)

# OCR 원본의 'YYYY-MM-00'을 월말 등으로 임의 보정하면 다른 방문과 합쳐질 수 있다.
# 따라서 day=00은 추정하지 않고 명시적으로 거부한다.
DATE_DAY_ZERO_POLICY = "reject"
CLINICAL_DATE_FIELDS = frozenset({"exam_date", "measured_at", "dob"})
_DAY_ZERO_RE = re.compile(r"^\s*\d{4}(?:[-/.]\d{1,2}[-/.]00|\d{2}00)(?:\D.*)?$")
# v2.3.2 (병원 피드백): 2자리 연도 날짜(예: '64-02-29' = 1964-02-29). 병원 실데이터가
#   생년을 2자리로 적는 경우가 있어, 통째로 버리지 않고 세기(19xx/20xx)를 추정해 받는다.
_TWO_DIGIT_YEAR_RE = re.compile(r"^\s*(\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\s*$")


def _resolve_two_digit_date(yy: int, mm: int, dd: int, today: date, *, past_only: bool):
    """2자리 연도 date 해석. 실재일(윤년 포함)은 date() 가 검증한다.
      - past_only=True(dob): 생년은 미래 불가 → 2000+yy 가 미래면 1900+yy.
        예 '64-02-29'→1964-02-29, '26-12-01'(오늘 이전 아니면)→1926-12-01.
      - past_only=False(검사일): 근래(20xx)로만 해석. 근미래 오타('27')는 100년 전으로
        둔갑시키지 않고 그대로 두어 상위 '미래 날짜' 검사가 거부하게 한다.
    실패 시 None."""
    year_candidates = (2000 + yy, 1900 + yy) if past_only else (2000 + yy,)
    for yr in year_candidates:
        try:
            d = date(yr, mm, dd)
        except ValueError:
            continue
        if past_only and d > today:
            continue
        return d
    return None


def validate_clinical_value(field: str, value: Any) -> tuple[Any | None, str | None]:
    """화이트리스트 임상값 1개 검증. 비대상 필드는 원값을 그대로 반환한다."""
    bounds = CLINICAL_RANGES.get(field)
    if bounds is None or value is None:
        return value, None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None, f"{field}: 숫자로 해석할 수 없는 값 {value!r}은 저장하지 않았습니다."
    if not math.isfinite(numeric):
        return None, f"{field}: 유한하지 않은 값 {value!r}은 저장하지 않았습니다."
    low, high = bounds
    if numeric < low or numeric > high:
        return None, (
            f"{field}: 값 {value!r}이 허용 범위 {low:g}~{high:g} 밖이어서 "
            "저장하지 않았습니다."
        )
    # 0/1 이진 플래그는 범위 안이어도 중간값(0.5 등)을 허용하지 않는다 — 임의 해석 방지.
    if field in BINARY_FIELDS and numeric not in (0.0, 1.0):
        return None, (
            f"{field}: 0 또는 1 이어야 하는 항목에 {value!r}이 들어와 저장하지 않았습니다."
        )
    return numeric, None


def validate_clinical_date(
    value: Any,
    *,
    field: str = "exam_date",
    today: date | None = None,
) -> tuple[date | None, str | None]:
    """날짜 1개를 엄격 파싱하고 실재일·미래일·day=00 정책을 검사한다.

    빈 값은 정상 결측(None)이다. 값이 있는데 파싱에 실패한 경우는 경고와 함께 None을
    반환하므로 호출자는 입력 경로에서 해당 행/요청을 거부할 수 있다.
    """
    if value is None:
        return None, None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        s = str(value).strip()
        if not s:
            return None, None
        if DATE_DAY_ZERO_POLICY == "reject" and _DAY_ZERO_RE.match(s):
            return None, f"{field}: 일(day)이 00인 날짜 {s!r}은 허용하지 않습니다."
        parsed = None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            # 흔한 ISO datetime 문자열은 날짜 부분이 유효할 때만 수용한다.
            try:
                parsed = datetime.fromisoformat(s).date()
            except (TypeError, ValueError):
                parsed = None
        if parsed is None:
            # v2.3.2: 2자리 연도('64-02-29' 등). strptime %Y 는 4자리만 받으므로 별도 처리.
            #   세기 추정(dob=과거, 검사일=근래)은 field 로 구분. 잘못된 날짜(예 1965-02-29)는 거부.
            m = _TWO_DIGIT_YEAR_RE.match(s)
            if m:
                yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                parsed = _resolve_two_digit_date(
                    yy, mm, dd, today or date.today(), past_only=(field == "dob")
                )
        if parsed is None:
            return None, f"{field}: 실재하지 않거나 지원하지 않는 날짜 {s!r}입니다."

    ref = today or date.today()
    if parsed > ref:
        return None, f"{field}: 미래 날짜 {parsed.isoformat()}은 허용하지 않습니다."
    return parsed, None


def sanitize_clinical_data(
    data: dict,
    *,
    today: date | None = None,
) -> tuple[dict, list[str]]:
    """입력 dict의 임상값/날짜를 공용 정책으로 정제하고 경고 목록을 반환한다.

    이상 수치는 키를 유지한 채 None으로 바꿔 호출자가 '측정하지 않은 값'처럼 다룰 수
    있게 한다. 날짜 오류도 None으로 바꾸지만, 저장 API는 경고가 있으면 행/요청 자체를
    거부해야 잘못된 날짜가 오늘로 대체되지 않는다.
    """
    out = dict(data)
    warnings: list[str] = []
    for field in CLINICAL_RANGES:
        if field not in out:
            continue
        value, warning = validate_clinical_value(field, out.get(field))
        out[field] = value
        if warning:
            warnings.append(warning)
    for field in CLINICAL_DATE_FIELDS:
        if field not in out:
            continue
        value, warning = validate_clinical_date(out.get(field), field=field, today=today)
        out[field] = value
        if warning:
            warnings.append(warning)
    return out, warnings

# v2.2.9: 방문 시점 전체 검사값 스냅샷(JSON) — 검사이력 페이지에서 방문별 전체 패널/위험도 산출용.
#   MeasurementHistory.snapshot 에 저장. 표시 + predict_all 재현에 필요한 입력 필드를 담는다.
SNAPSHOT_FIELDS = [
    "age", "sex", "dob", "exam_date",
    "hba1c", "fbg", "c_peptide",
    "total_cholesterol", "triglycerides", "hdl", "ldl",
    "cr", "ast", "alt", "ggt",
    "sbp", "dbp", "hypertension",
    "height", "weight", "bmi", "visceral_fat",
    "he_upro", "he_uglu", "he_ubld", "urine_bil", "urine_uro",
    "urine_ket", "urine_nit", "urine_ph", "urine_sg",
    "smoking", "drinking", "exercise", "sleep_hours",
    "dm_diagnosis_age", "dm_duration", "dm_medication", "insulin_medication",
]


def visit_snapshot(data: dict) -> str:
    """방문 시점 검사값 dict → 검증된 JSON 문자열. 날짜는 ISO 문자열로."""
    clean, _ = sanitize_clinical_data(data)
    out = {}
    for k in SNAPSHOT_FIELDS:
        v = clean.get(k)
        if v is None:
            continue
        out[k] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return json.dumps(out, ensure_ascii=False)


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
    """str/date/datetime → 검증된 date. 실패·미래 날짜는 None."""
    parsed, _ = validate_clinical_date(v)
    return parsed


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


def normalize_sex(v) -> str | None:
    """성별 표기를 'M'/'F' 로 단일 정규화. 인식 불가/결측은 None.

    업로드(CSV/엑셀)·수기 POST·모델 입력·eGFR 계산이 모두 이 함수를 공유해
    '남'/'여'/'male'/'M'/'1' 등 다양한 병원 표기를 일관 처리하고,
    인식 불가/결측 값을 임의로 여성으로 처리하지 않는다(임상값 왜곡 방지).
    """
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("M", "MALE", "남", "남자", "1", "1.0"):
        return "M"
    if s in ("F", "FEMALE", "여", "여자", "2", "2.0"):
        return "F"
    return None


def _ckd_epi_egfr(cr: float, age: float, sex: str) -> float | None:
    """
    CKD-EPI 2009 공식. sex 는 normalize_sex 로 'M'/'F' 정규화 후 사용.
    반환: eGFR (mL/min/1.73m²), 계산 불가(성별 불명 포함) 시 None.
    """
    nsex = normalize_sex(sex)
    if cr is None or age is None or nsex is None:
        return None
    if cr <= 0 or age <= 0:
        return None
    is_male = nsex == "M"
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
    # 라우터 밖의 재계산/조회 경로에서도 명백한 원본 outlier가 파생값으로 전파되지 않게 방어.
    # 저장 경로는 호출 전 sanitizer에서 동일 경고를 수집한다.
    out, _ = sanitize_clinical_data(data)

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
    # v2.3.0 (감사): 역추정값을 out 에 저장하지 않아 업로드 필수값 검사
    #   (missing_required_fields)가 'C-peptide 누락'으로 행을 거부하던 문제 수정.
    #   CLAUDE.md 하위호환 규칙(c_peptide = he_insulin / 3.0)대로 저장까지 수행한다.
    if c_peptide is None and he_insulin is not None:
        estimated_cpep = round(he_insulin / 3.0, 2)
        c_peptide, _ = validate_clinical_value("c_peptide", estimated_cpep)
        if c_peptide is not None and out.get("c_peptide") is None:
            out["c_peptide"] = c_peptide

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
