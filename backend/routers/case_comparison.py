"""
유사 사례 비교 API (v2.0 — 실 데이터 기반)
==============================================
**알고리즘:**
  - 본인 제외 등록 환자들과 가중치 기반 거리 (정규화된 weighted L1) 계산
  - 거리 → 유사도(%) 선형 매핑, 상위 3건 반환
  - 비교 가능 변수가 하나도 없는 후보는 제외
  - 다른 환자가 0명이면 빈 결과 → 프론트에서 '유사 사례 없음' 안내

**가중치 (사용자 지정 우선순위):**
  HbA1c (5.0) > C-peptide (4.5) > age (4.0) > dm_duration (3.5) > sex (3.0)
  > fbg (2.5) ≈ eGFR (2.5) > SBP (2.0) ≈ BMI (2.0) > LDL/HDL (1.5) > TG (1.0)

NULL 값은 페널티 없이 스킵 (양쪽 다 입력된 변수만 비교에 사용).
"""
from __future__ import annotations
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db, Patient, MeasurementHistory
from ml.predictor import predict_all

router = APIRouter(prefix="/api/v1", tags=["case_comparison"])


# ── 유사도 가중치 (사용자 지정 우선순위) ─────────────────────────
# weight: 상대적 중요도 (높을수록 매칭 영향 큼)
# scale:  단위 1 정규화 기준 (예 hba1c scale=1.0 → 1% 차이가 1 unit)
SIMILARITY_WEIGHTS: dict[str, dict] = {
    "hba1c":         {"weight": 5.0, "scale": 1.0,  "label": "HbA1c (당화혈색소)"},
    "c_peptide":     {"weight": 4.5, "scale": 1.0,  "label": "C-peptide"},
    "age":           {"weight": 4.0, "scale": 5.0,  "label": "나이"},
    "dm_duration":   {"weight": 3.5, "scale": 3.0,  "label": "당뇨 유병 기간"},
    "fbg":           {"weight": 2.5, "scale": 30.0, "label": "공복혈당"},
    "egfr":          {"weight": 2.5, "scale": 15.0, "label": "eGFR (신기능)"},
    "sbp":           {"weight": 2.0, "scale": 15.0, "label": "수축기 혈압"},
    "bmi":           {"weight": 2.0, "scale": 3.0,  "label": "BMI"},
    "ldl":           {"weight": 1.5, "scale": 30.0, "label": "LDL 콜레스테롤"},
    "hdl":           {"weight": 1.5, "scale": 10.0, "label": "HDL 콜레스테롤"},
    "triglycerides": {"weight": 1.0, "scale": 50.0, "label": "중성지방"},
}
# 성별은 binary (일치 0, 불일치 1)
SEX_WEIGHT = 3.0


def _patient_compare_dict(p: Patient) -> dict:
    """유사도 계산에 쓰는 컬럼만 추출."""
    keys = list(SIMILARITY_WEIGHTS.keys()) + ["sex"]
    return {k: getattr(p, k, None) for k in keys}


def _similarity_distance(a: dict, b: dict) -> tuple[float, float]:
    """
    가중 정규화 L1 거리 + 사용된 가중치 합 반환.
    NULL 인 변수는 한쪽이라도 비어 있으면 스킵 (페널티 없음).
    """
    total_dist = 0.0
    total_weight = 0.0

    for key, conf in SIMILARITY_WEIGHTS.items():
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None:
            continue
        try:
            diff = abs(float(va) - float(vb)) / conf["scale"]
        except (TypeError, ValueError):
            continue
        total_dist += conf["weight"] * diff
        total_weight += conf["weight"]

    sa, sb = a.get("sex"), b.get("sex")
    if sa is not None and sb is not None:
        total_dist += SEX_WEIGHT * (0.0 if sa == sb else 1.0)
        total_weight += SEX_WEIGHT

    return total_dist, total_weight


def _distance_to_similarity(distance: float, weight_used: float) -> int:
    """
    가중평균 정규화 거리 → 0~99% 유사도.
      - 단위거리 0.0  → 100%  (모든 변수 일치)
      - 단위거리 0.5  → 85%   (각 변수 평균 0.5 unit 차이)
      - 단위거리 1.0  → 70%
      - 단위거리 2.0  → 40% 클램프
    """
    if weight_used <= 0:
        return 0
    norm = distance / weight_used
    sim = 100.0 - norm * 30.0
    return max(40, min(99, round(sim)))


def _mask_name(name: str | None) -> str:
    """이름 마스킹 — 김영호 → 김*호 / 박미 → 박* / 김OO환 → 김**환"""
    if not name:
        return "환자"
    n = name.strip()
    if len(n) <= 1:
        return n
    if len(n) == 2:
        return n[0] + "*"
    return n[0] + "*" * (len(n) - 2) + n[-1]



def _all_measurements(db: Session, pid: int) -> list[MeasurementHistory]:
    """환자 측정 이력 전체 (오름차순)."""
    return (
        db.query(MeasurementHistory)
        .filter(MeasurementHistory.patient_id == pid)
        .order_by(MeasurementHistory.measured_at.asc())
        .all()
    )


def _treatment_months(p: Patient, rows: list[MeasurementHistory]) -> int | None:
    """
    가장 오래된 측정일 또는 patient.exam_date 부터 오늘까지의 개월 수.
    값이 미래거나 결정 불가능하면 None.
    """
    candidates: list[date] = [r.measured_at for r in rows if r.measured_at is not None]
    if p.exam_date is not None:
        candidates.append(p.exam_date)
    if not candidates:
        return None
    oldest = min(candidates)
    today = date.today()
    days = (today - oldest).days
    if days < 0:
        return None
    return max(0, days // 30)


def _current_age(p: Patient) -> int | None:
    """
    현재 만 나이 — dob 기반으로 매 조회마다 재계산.
    dob 가 없을 때만 stale 한 patient.age 컬럼으로 fallback.
    DB 의 patient.age 는 입력 시점의 값이라 해를 넘기면 실제 나이와 어긋나므로
    가능하면 항상 dob 에서 계산해야 한다.
    """
    today = date.today()
    if p.dob is not None:
        a = today.year - p.dob.year - ((today.month, today.day) < (p.dob.month, p.dob.day))
        if 0 <= a <= 120:
            return a
    if p.age is not None:
        try:
            return int(p.age)
        except (TypeError, ValueError):
            return None
    return None


def _calc_dx_years(p: Patient) -> int | None:
    """
    당뇨 이환 기간 = 현재 만 나이 - 진단 시 나이.
    매 조회 시 _current_age(p) 로 동적 계산하므로 해가 바뀌면 자동으로 +1.
    예) 1961년생, 진단 나이 64세, 오늘 2026년 → 현재 만 65세, 이환 1년차.
    """
    if p.dm_diagnosis_age is None:
        return None
    cur = _current_age(p)
    if cur is None:
        return None
    years = cur - int(p.dm_diagnosis_age)
    return years if 0 <= years <= 120 else None


def _ml_predict_with_override(patient_data: dict, mh: MeasurementHistory | None) -> dict:
    """
    measurement row 의 hba1c / c_peptide / cr 값으로 patient_data 일부를 덮어쓰고 ML 예측.
    mh 가 None 이면 patient 현재값 그대로 사용.
    """
    pdata = dict(patient_data)
    if mh is not None:
        if mh.hba1c is not None:
            pdata["hba1c"] = mh.hba1c
        if mh.c_peptide is not None:
            pdata["c_peptide"] = mh.c_peptide
        if mh.cr is not None:
            pdata["cr"] = mh.cr
    return predict_all(pdata)


def _build_complications(
    patient_data: dict,
    mh_oldest: MeasurementHistory | None,
    mh_newest: MeasurementHistory | None,
) -> dict:
    """
    실 ML 모델로 합병증 위험도 before / after 산출.

    - 이력 ≥ 2: oldest 측정값(=초기 합병증 위험) vs newest(=현재 위험) 두 번 예측
    - 이력 ≤ 1: 한 번만 예측, before == after (시간 흐름 비교 불가능 → 변화 없음 표시)

    pkl 미구현 모델(neuro/dementia/cerebro)은 None → 카드에서 자동 제외.
    """
    pred_before = _ml_predict_with_override(patient_data, mh_oldest)
    same_row = mh_oldest is None or mh_newest is None or mh_oldest is mh_newest \
        or (mh_oldest.id == mh_newest.id if hasattr(mh_oldest, 'id') else False)
    pred_after = pred_before if same_row else _ml_predict_with_override(patient_data, mh_newest)

    name_map = {
        "kidney_disease": ("kidney", "당뇨병성 신장질환"),
        "cardiovascular": ("cardio", "심혈관 질환"),
        "retinopathy":    ("retina", "망막병증"),
    }
    out: dict[str, dict] = {}
    for full, (short, label) in name_map.items():
        b = (pred_before.get(full) or {}).get("score")
        a = (pred_after.get(full) or {}).get("score")
        if b is None and a is None:
            continue
        bf = int(round(b)) if b is not None else None
        af = int(round(a)) if a is not None else bf
        if bf is None:
            bf = af
        out[short] = {
            "name": label,
            "before_pct": bf,
            "after_pct": af,
        }
    return out


def _criteria_payload() -> list[dict]:
    """프론트의 알고리즘 투명성 표시용 가중치 목록 (내림차순)."""
    items = [
        {"key": k, "label": v["label"], "weight": v["weight"]}
        for k, v in SIMILARITY_WEIGHTS.items()
    ]
    items.append({"key": "sex", "label": "성별", "weight": SEX_WEIGHT})
    items.sort(key=lambda x: -x["weight"])
    return items


@router.get("/case-comparison/{patient_id}")
def get_case_comparison(patient_id: int, db: Session = Depends(get_db)):
    me = db.query(Patient).filter(Patient.id == patient_id).first()
    if not me:
        raise HTTPException(status_code=404, detail="Patient not found")

    me_dict = _patient_compare_dict(me)

    # 본인 제외 모든 환자
    others = db.query(Patient).filter(Patient.id != patient_id).all()

    # 다른 환자가 한 명도 없으면 빈 결과 (프론트가 '유사 사례 없음' 표시)
    if not others:
        return {
            "data": {
                "patient_name": me.name,
                "cases": [],
                "total_compared": 0,
                "criteria": _criteria_payload(),
            },
            "success": True,
        }

    # 가중 거리 계산
    scored: list[tuple[int, Patient, float]] = []
    for o in others:
        o_dict = _patient_compare_dict(o)
        dist, w = _similarity_distance(me_dict, o_dict)
        if w <= 0:
            # 비교 가능한 변수가 하나도 없으면 후보 제외
            continue
        sim = _distance_to_similarity(dist, w)
        scored.append((sim, o, dist))

    if not scored:
        return {
            "data": {
                "patient_name": me.name,
                "cases": [],
                "total_compared": len(others),
                "criteria": _criteria_payload(),
            },
            "success": True,
        }

    # 유사도 내림차순 → 동률이면 절대거리 오름차순
    scored.sort(key=lambda x: (-x[0], x[2]))
    top = scored[:3]

    cases: list[dict] = []
    for sim, p, _dist in top:
        p_data = {c.name: getattr(p, c.name) for c in p.__table__.columns}

        # 측정 이력 oldest / newest — 합병증 before/after 와 표시값 모두 여기서 결정
        rows = _all_measurements(db, p.id)
        rows_hb = [r for r in rows if r.hba1c is not None]
        rows_cp = [r for r in rows if r.c_peptide is not None]

        mh_oldest = rows[0] if rows else None
        mh_newest = rows[-1] if rows else None

        # 합병증 ML 예측 — 초기 측정 vs 최신 측정으로 before/after 분리
        comps = _build_complications(p_data, mh_oldest, mh_newest)

        # HbA1c 변화 (이력 ≥ 2 일 때만 표시, 1 이하면 None)
        hb_before = round(rows_hb[0].hba1c, 1) if len(rows_hb) >= 2 else None
        hb_after = round(rows_hb[-1].hba1c, 1) if len(rows_hb) >= 2 else None

        # C-peptide 변화 (이력 ≥ 2 일 때만)
        cp_before = round(rows_cp[0].c_peptide, 2) if len(rows_cp) >= 2 else None
        cp_after = round(rows_cp[-1].c_peptide, 2) if len(rows_cp) >= 2 else None

        # 치료 기간 — oldest 측정일 or patient.exam_date 부터 오늘까지
        months = _treatment_months(p, rows)

        # HbA1c 개선폭 (이력 있으면 실측, 없으면 모름)
        improvement = None
        if hb_before is not None and hb_after is not None:
            improvement = round(hb_before - hb_after, 1)

        # 비용 절감 / 기대 건강수명 — 실제 개선폭이 있으면 그걸 반영, 없으면 합병증 평균 기반
        avg_after = (
            sum(c["after_pct"] for c in comps.values()) / len(comps)
            if comps else 30.0
        )
        if improvement is not None and improvement > 0:
            cost_saving = int(max(150, min(900, improvement * 220 + (sim - 50) * 5)))
        else:
            # 이력 없는 경우: 합병증 점수와 유사도로 추정 (낮을수록 절감 큼)
            cost_saving = int(max(150, min(900, (100 - avg_after) * 6 + (sim - 50) * 4)))

        age_now = p.age or 65
        age_pen = max(0.0, age_now - 60) * 0.3
        gain_bonus = (improvement or 1.0) * 1.5
        expected = max(70, min(85, round(82 - age_pen + gain_bonus)))

        # HbA1c / C-peptide "최신 단일 시점" — 이력 있으면 newest, 없으면 patient 컬럼 fallback
        hba1c_current: float | None = None
        if rows_hb:
            hba1c_current = round(rows_hb[-1].hba1c, 1)
        elif p.hba1c is not None:
            hba1c_current = round(p.hba1c, 1)

        cpep_current: float | None = None
        if rows_cp:
            cpep_current = round(rows_cp[-1].c_peptide, 2)
        elif p.c_peptide is not None:
            cpep_current = round(p.c_peptide, 2)

        # 진단 경과 — patient.dm_duration 은 입력 시점 stale 값. 매 조회마다 오늘 기준 재계산.
        dx_years = _calc_dx_years(p)

        cases.append({
            "id": p.id,
            "name": _mask_name(p.name),
            "age": _current_age(p),
            "sex": p.sex,
            "similarity_pct": int(sim),
            "dx_years": dx_years,
            "hba1c_before": hb_before,
            "hba1c_after": hb_after,
            "c_peptide_before": cp_before,
            "c_peptide_after": cp_after,
            "hba1c_current": hba1c_current,
            "c_peptide_current": cpep_current,
            "treatment_months": months,
            "treatment_type": "집중케어" if (improvement and improvement >= 1.0) else "일반관리",
            "complications": comps,
            "cost_saving_annual_man": cost_saving,
            "expected_healthy_age": int(expected),
        })

    return {
        "data": {
            "patient_name": me.name,
            "cases": cases,
            "total_compared": len(others),
            "criteria": _criteria_payload(),
        },
        "success": True,
    }
