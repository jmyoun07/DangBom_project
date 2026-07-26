"""졸업자 엑셀('졸업자 리스트' 시트) 파서 + DB 적재.

Settings 에서 업로드한 xlsx 를 파싱해 Graduate 테이블을 통째로 교체한다.
원본이 수기 데이터라 값이 지저분(당뇨약 개수에 '단약'/'많이' 등)하므로 숫자만 안전 추출하고,
유사사례 매칭에 필요한 핵심 필드만 정규화한다. (C-peptide·GFR·합병증 점수는 원본에 없음 → None)
"""
from __future__ import annotations

import io
import json
import math
import re

import pandas as pd

from services.derived import normalize_sex

SHEET_NAME = "졸업자 리스트"


def _num(v):
    """숫자 추출. 숫자형이면 그대로, 문자열이면 첫 숫자만('2알'→2, '약 3개월'→3).
    추출 불가('단약','많이' 등)·NaN·None → None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except (TypeError, ValueError):
            return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))  # 천단위 콤마 제거
    return float(m.group()) if m else None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _str(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def _sex(v):
    # v2.3.0 (감사): 앱 전체 성별 정규화 단일 소스(services.derived.normalize_sex) 사용.
    #   기존 자체 구현은 'male'/'female'/'1.0' 표기를 놓쳤다.
    return normalize_sex(v)


# ── long 포맷(환자당 초진/졸업 2행) 지원 ───────────────────────────────
# 병원이 주는 raw 데이터셋(졸업자_raw_데이터셋_416행)은 wide 가 아니라 long 이다.
#   patient_id, visit_type('초진'|'졸업'), hba1c, c_peptide, cr, egfr, ... 48컬럼
# wide('졸업자 리스트' 시트)와 달리 C-peptide·eGFR·소변 등 모델 변수가 전부 들어있어
# 유사사례의 '치료 전/후 변화'를 실제 값으로 보여줄 수 있다.
_LONG_REQUIRED = {"visit_type", "hba1c"}
_INIT_LABELS = {"초진", "치료전", "before", "pre"}
_GRAD_LABELS = {"졸업", "치료후", "after", "post"}

# 유사사례 화면이 쓰는 합병증 점수 키(있으면 comp_before/after 로 직렬화)
_COMP_KEYS = ("neuro", "retina", "kidney", "cardio", "cerebro", "dementia")


def _read_table(content: bytes) -> "pd.DataFrame | None":
    """csv/xlsx bytes → DataFrame. 실패 시 None."""
    for reader in (
        lambda: pd.read_csv(io.BytesIO(content), encoding="utf-8-sig"),
        lambda: pd.read_csv(io.BytesIO(content), encoding="cp949"),
    ):
        try:
            df = reader()
            if len(df.columns) > 1:
                return df
        except Exception:
            continue
    return None


# 모델 질환명 → 화면 짧은 키
_MODEL_TO_SHORT = {
    "neuropathy": "neuro", "retinopathy": "retina", "kidney_disease": "kidney",
    "cardiovascular": "cardio", "cerebrovascular": "cerebro", "dementia": "dementia",
}


def _derive_age(dob, visit_date):
    """dob + 검사일 → 만 나이. 둘 중 하나라도 없거나 파싱 실패면 None.
    v2.3.5: 병원이 나이를 직접 계산해 적지 않아도 되게 한다."""
    from services.derived import _to_date, _age_from_dob
    d = _to_date(dob)
    if d is None:
        return None
    return _age_from_dob(d, _to_date(visit_date))


def _derive_egfr(cr, age, sex):
    """CKD-EPI eGFR — 앱 전체와 동일 공식(services.derived) 사용."""
    if cr is None or age is None or not sex:
        return None
    from services.derived import _ckd_epi_egfr
    return _ckd_epi_egfr(cr, age, sex)


def _derive_bmi(height, weight):
    if not height or not weight or height <= 0:
        return None
    return round(weight / ((height / 100.0) ** 2), 1)


def _row_to_model_input(row) -> dict:
    """졸업자 raw 행 → predict_all 입력 dict.

    raw 데이터셋은 모델 변수 48개를 모두 담고 있어(필수 13항목 포함) 그대로 예측 가능하다.
    컬럼명이 Patient 필드와 거의 동일하고, 개월 단위인 dm_duration_months 만 연 단위로 환산한다.
    """
    d = {}
    for k in row.index:
        v = row.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)) or v == "":
            continue
        n = _num(v) if not isinstance(v, str) or re.fullmatch(r"-?\d+(?:\.\d+)?", v.strip()) else None
        d[str(k)] = n if n is not None else v
    months = _num(row.get("dm_duration_months")) if "dm_duration_months" in row.index else None
    if months is not None:
        d["dm_duration"] = round(months / 12.0, 1)
    return d


def _predict_comp(row) -> dict:
    """졸업자 한 시점(초진 or 졸업)의 6개 합병증 위험 점수를 ML 로 산출.

    유사사례 화면의 '합병증 위험도 전/후' 바에 쓰인다. 예측 불가(필수검사 누락 등)면
    빈 dict → 화면은 기존대로 '데이터 보강 후 표시' 안내를 띄운다.
    """
    try:
        from ml.predictor import predict_all
        preds = predict_all(_row_to_model_input(row))
    except Exception:
        return {}
    out = {}
    for model_name, short in _MODEL_TO_SHORT.items():
        p = preds.get(model_name) or {}
        if not p.get("available"):
            continue
        score = p.get("display_score")
        if score is None:
            score = p.get("score")
        if score is not None:
            out[short] = round(float(score), 1)
    return out


def _visit_kind(v) -> str | None:
    s = (_str(v) or "").strip().lower()
    if s in {x.lower() for x in _INIT_LABELS}:
        return "init"
    if s in {x.lower() for x in _GRAD_LABELS}:
        return "grad"
    return None


def parse_graduates_long(df) -> list[dict]:
    """long 포맷 DataFrame → Graduate dict 리스트.

    환자별로 초진행/졸업행을 짝지어 before/after 를 만든다. 초진·졸업이 모두 있고
    HbA1c 가 양쪽에 있는 환자만 채택(유사사례 매칭에 필수).
    """
    if not _LONG_REQUIRED.issubset({str(c).strip() for c in df.columns}):
        return []

    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    key_col = "patient_id" if "patient_id" in df.columns else (
        "chart_no" if "chart_no" in df.columns else None)
    if key_col is None:
        return []

    groups: dict[str, dict[str, dict]] = {}
    for _, r in df.iterrows():
        kind = _visit_kind(r.get("visit_type"))
        key = _str(r.get(key_col))
        if kind is None or key is None:
            continue
        groups.setdefault(key, {})[kind] = r

    def g(row, *names):
        for n in names:
            if row is not None and n in row.index:
                v = row.get(n)
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    return v
        return None

    out = []
    for key, pair in groups.items():
        a, b = pair.get("init"), pair.get("grad")
        if a is None or b is None:
            continue
        before, after = _num(g(a, "hba1c")), _num(g(b, "hba1c"))
        if before is None or after is None:
            continue

        # 합병증 위험도 전/후 — 원본에 comp_* 컬럼이 있으면 그대로 쓰고,
        #   없으면 raw 데이터셋의 모델 변수로 직접 예측해 산출한다(아래 _predict_comp).
        comp_b = {k: _num(g(a, f"comp_{k}")) for k in _COMP_KEYS if _num(g(a, f"comp_{k}")) is not None}
        comp_a = {k: _num(g(b, f"comp_{k}")) for k in _COMP_KEYS if _num(g(b, f"comp_{k}")) is not None}
        if not comp_b:
            comp_b = _predict_comp(a)
        if not comp_a:
            comp_a = _predict_comp(b)

        # v2.3.5: age·eGFR·BMI 는 병원이 손으로 계산하지 않아도 되도록 자동 파생.
        #   age  = dob + visit_date (없으면 입력된 age 사용)
        #   eGFR = CKD-EPI(cr, age, sex)  — 신장 기능 회복 사례 판정에 쓰임
        #   BMI  = weight / (height/100)^2
        _sex_v = _sex(g(a, "sex"))
        _age = _int(g(a, "age")) or _derive_age(g(a, "dob"), g(a, "visit_date"))
        _age_b = _int(g(b, "age")) or _derive_age(g(b, "dob"), g(b, "visit_date")) or _age
        egfr_b = _num(g(a, "egfr")) or _derive_egfr(_num(g(a, "cr")), _age, _sex_v)
        egfr_a = _num(g(b, "egfr")) or _derive_egfr(_num(g(b, "cr")), _age_b, _sex_v)
        out.append({
            "chart_no": _str(g(a, "chart_no")) or key,
            "name": _str(g(a, "name")),
            "sex": _sex_v,
            "age": _age,
            "treatment_months": _int(g(a, "treatment_months")) or _int(g(b, "treatment_months")),
            "dm_duration_months": _int(g(a, "dm_duration_months")),
            "init_bmi": _num(g(a, "bmi", "init_bmi")) or _derive_bmi(
                _num(g(a, "height")), _num(g(a, "weight"))),
            "dm_med_count": _num(g(a, "dm_med_count")),
            "hba1c_before": before,
            "hba1c_after": after,
            "hba1c_drop": round(before - after, 2),
            "neuro_improve": _str(g(a, "neuro_improve")),
            "goal": _str(g(a, "goal")),
            "cpep_before": _num(g(a, "c_peptide")),
            "cpep_after": _num(g(b, "c_peptide")),
            "egfr_before": egfr_b,
            "egfr_after": egfr_a,
            "egfr": egfr_b,
            "comp_before": json.dumps(comp_b, ensure_ascii=False) if comp_b else None,
            "comp_after": json.dumps(comp_a, ensure_ascii=False) if comp_a else None,
        })
    return out


def parse_graduates_any(content: bytes) -> list[dict]:
    """csv/xlsx 를 자동 판별해 파싱. long 포맷 우선, 없으면 기존 wide 시트."""
    df = _read_table(content)
    if df is not None:
        rows = parse_graduates_long(df)
        if rows:
            return rows
    try:
        return parse_graduates(content)
    except Exception:
        # csv 인데 wide 파서가 실패한 경우 — long 시도조차 못 했으면 빈 결과.
        return []


def parse_graduates(content: bytes) -> list[dict]:
    """xlsx bytes → Graduate dict 리스트. '졸업자 리스트' 시트 사용.
    치료전/치료후 HbA1c 가 둘 다 있는 행만 채택(유사사례에 필수).

    xlsx 안에 long 포맷 시트가 있으면 그쪽을 우선 사용한다."""
    xls = pd.ExcelFile(io.BytesIO(content))
    # long 포맷 시트(visit_type 컬럼 보유)가 있으면 우선
    for _sn in xls.sheet_names:
        try:
            _df = pd.read_excel(xls, sheet_name=_sn)
        except Exception:
            continue
        _long = parse_graduates_long(_df)
        if _long:
            return _long
    sheet = SHEET_NAME if SHEET_NAME in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet)

    def col(*names):
        for n in names:
            if n in df.columns:
                return n
        return None

    c_chart = col("챠트번호", "차트번호")
    c_name = col("환자명", "이름")
    c_sex = col("성별")
    c_age = col("결제일 기준 나이", "나이")
    c_tx = col("한약복용기간")
    c_dur = col("유병기간(개월차)", "유병기간(개월)")
    c_bmi = col("초진BMI", "초진 BMI")
    c_med = col("당뇨약 개수")
    c_bef = col("치료전")
    c_aft = col("치료후")
    c_drop = col("감소 차이")
    c_neuro = col("호전 정도")   # 당뇨발저림 호전 정도 (첫 번째)
    c_goal = col("목표")
    # ── 6/13 보강 컬럼 (C-peptide·eGFR·합병증 전/후) — 있으면 읽고, 없으면 None ──
    c_cpep_b = col("C펩타이드_치료전", "C-peptide_치료전", "C펩타이드 치료전")
    c_cpep_a = col("C펩타이드_치료후", "C-peptide_치료후", "C펩타이드 치료후")
    c_egfr_b = col("eGFR_치료전", "eGFR 치료전", "신장_치료전")
    c_egfr_a = col("eGFR_치료후", "eGFR 치료후", "신장_치료후")
    COMP_COLS = {
        "neuro":    (col("말초신경병증_치료전", "말초신경병증 치료전"), col("말초신경병증_치료후", "말초신경병증 치료후")),
        "retina":   (col("망막병증_치료전", "망막병증 치료전"), col("망막병증_치료후", "망막병증 치료후")),
        "kidney":   (col("신장질환_치료전", "신장질환 치료전"), col("신장질환_치료후", "신장질환 치료후")),
        "cardio":   (col("심혈관질환_치료전", "심혈관질환 치료전"), col("심혈관질환_치료후", "심혈관질환 치료후")),
        "cerebro":  (col("뇌혈관질환_치료전", "뇌혈관질환 치료전"), col("뇌혈관질환_치료후", "뇌혈관질환 치료후")),
        "dementia": (col("치매_치료전", "치매 치료전"), col("치매_치료후", "치매 치료후")),
    }

    if c_bef is None or c_aft is None:
        raise ValueError("'치료전'/'치료후'(HbA1c) 컬럼을 찾을 수 없습니다. '졸업자 리스트' 시트 형식을 확인하세요.")

    rows = []
    for _, r in df.iterrows():
        before = _num(r.get(c_bef))
        after = _num(r.get(c_aft))
        if before is None or after is None:
            continue
        drop = _num(r.get(c_drop)) if c_drop else None
        if drop is None:
            drop = round(before - after, 2)
        cpep_b = _num(r.get(c_cpep_b)) if c_cpep_b else None
        cpep_a = _num(r.get(c_cpep_a)) if c_cpep_a else None
        egfr_b = _num(r.get(c_egfr_b)) if c_egfr_b else None
        egfr_a = _num(r.get(c_egfr_a)) if c_egfr_a else None
        comp_b, comp_a = {}, {}
        for _k, (_cb, _ca) in COMP_COLS.items():
            _vb = _num(r.get(_cb)) if _cb else None
            _va = _num(r.get(_ca)) if _ca else None
            if _vb is not None:
                comp_b[_k] = _vb
            if _va is not None:
                comp_a[_k] = _va
        rows.append({
            "chart_no": _str(r.get(c_chart)) if c_chart else None,
            "name": _str(r.get(c_name)) if c_name else None,
            "sex": _sex(r.get(c_sex)) if c_sex else None,
            "age": _int(r.get(c_age)) if c_age else None,
            "treatment_months": _int(r.get(c_tx)) if c_tx else None,
            "dm_duration_months": _int(r.get(c_dur)) if c_dur else None,
            "init_bmi": _num(r.get(c_bmi)) if c_bmi else None,
            "dm_med_count": _num(r.get(c_med)) if c_med else None,
            "hba1c_before": before,
            "hba1c_after": after,
            "hba1c_drop": drop,
            "neuro_improve": _str(r.get(c_neuro)) if c_neuro else None,
            "goal": _str(r.get(c_goal)) if c_goal else None,
            "cpep_before": cpep_b, "cpep_after": cpep_a,
            "egfr_before": egfr_b, "egfr_after": egfr_a,
            "egfr": egfr_b,  # 단일 하위호환 = 치료전 eGFR
            "comp_before": json.dumps(comp_b, ensure_ascii=False) if comp_b else None,
            "comp_after": json.dumps(comp_a, ensure_ascii=False) if comp_a else None,
        })
    return rows


def load_into_db(db, rows: list[dict]) -> int:
    """Graduate 테이블을 통째로 교체하고 적재한 행 수를 반환."""
    from models.database import Graduate
    db.query(Graduate).delete()
    for d in rows:
        db.add(Graduate(**d))
    db.commit()
    return len(rows)


# ── 프로젝트 폴더의 졸업자 원본을 자동 반영 ─────────────────────────────
# 병원이 이 파일을 계속 갱신하므로, 서버 시작 시 '가장 최근에 수정된' 파일을 읽어
# 내용이 바뀌었을 때만 다시 적재한다(해시 비교 → 불필요한 재적재/로그 방지).
_SOURCE_GLOBS = ("졸업자_raw_데이터셋*.csv", "졸업자_raw_데이터셋*.xlsx")
_STAMP_NAME = ".graduates_source.sha256"


def find_source_file(project_root) -> "Path | None":
    """프로젝트 루트에서 가장 최근 수정된 졸업자 raw 파일 경로."""
    from pathlib import Path
    root = Path(project_root)
    hits = []
    for pat in _SOURCE_GLOBS:
        hits.extend(root.glob(pat))
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)


def sync_from_project_file(db, project_root, force: bool = False) -> dict:
    """프로젝트 폴더의 졸업자 원본을 읽어 Graduate 테이블에 반영.

    반환: {"status": "loaded"|"unchanged"|"missing"|"failed", "loaded": n, "file": name}
    """
    import hashlib
    from pathlib import Path
    from models.database import Graduate

    src = find_source_file(project_root)
    if src is None:
        return {"status": "missing", "loaded": 0, "file": None}

    content = src.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    stamp = Path(project_root) / "backend" / _STAMP_NAME
    prev = stamp.read_text().strip() if stamp.exists() else ""

    if not force and prev == digest and db.query(Graduate).count() > 0:
        return {"status": "unchanged", "loaded": 0, "file": src.name}

    rows = parse_graduates_any(content)
    if not rows:
        return {"status": "failed", "loaded": 0, "file": src.name}

    n = load_into_db(db, rows)
    try:
        stamp.write_text(digest)
    except Exception:
        pass       # 스탬프 실패는 치명적이지 않음 — 다음 기동에서 재적재될 뿐
    return {"status": "loaded", "loaded": n, "file": src.name}
