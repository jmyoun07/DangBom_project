"""유사 사례 비교 API (v3.0 — 졸업자 데이터 기반)
==================================================
6/8 피드백 반영:
  - 환자 리스트가 아니라 '전지점 졸업자' 데이터(Graduate 테이블)에서 유사 사례를 찾는다.
  - 치료기간 1년(12개월) 이내 졸업자만 후보.
  - 카드 2개:
      ① 당화혈색소 유사: 환자 HbA1c 와 가장 가까운(약간 더 높은 쪽 우선) 졸업자.
      ② 최악 피쳐 + 극적 개선: 환자의 가장 취약한 지표(나이/HbA1c/유병기간/BMI)와 비슷하면서
         그 유형에서 가장 극적으로 좋아진 졸업자.
  - 치료 전/후 HbA1c·당뇨약 개수 표시, 의료비/건강수명은 '증감'(예: -184만원, +9세).
  - 합병증 위험 변화·GFR(<60) 기반 사례는 원본 엑셀에 데이터가 없어 골격만 — 데이터 보강 시 연결.

데이터 적재: Settings 에서 졸업자 xlsx 업로드 → services/graduates.py → Graduate 테이블.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db, Patient, Graduate, MeasurementHistory
from services.derived import current_age as _current_age_calc
from services.derived import current_dm_duration as _current_dm_dur_calc
from services.outcome_model import treatment_outcome

router = APIRouter(prefix="/api/v1", tags=["case_comparison"])

TREATMENT_MONTHS_MAX = 12   # 치료기간 1년 이내만 후보


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _mask_name(name: str | None) -> str:
    if not name:
        return "졸업자"
    n = name.strip()
    if len(n) <= 1:
        return n
    if len(n) == 2:
        return n[0] + "*"
    return n[0] + "*" * (len(n) - 2) + n[-1]


def _patient_to_dict(p: Patient) -> dict:
    return {c.name: getattr(p, c.name) for c in p.__table__.columns}


def _worst_feature(hba1c, age, dm_years, bmi):
    """환자의 가장 취약한(severity 최고) 지표를 고른다."""
    sev = {}
    if hba1c is not None:
        sev["hba1c"] = _clamp((hba1c - 6.0) / 6.0, 0.0, 1.0)
    if age is not None:
        sev["age"] = _clamp((age - 50) / 30.0, 0.0, 1.0)
    if dm_years is not None:
        sev["dm_duration"] = _clamp((dm_years - 5) / 25.0, 0.0, 1.0)
    if bmi is not None:
        sev["bmi"] = _clamp((bmi - 25) / 10.0, 0.0, 1.0)
    if not sev:
        return None
    return max(sev, key=lambda k: sev[k])


_FEATURE_LABEL = {
    "hba1c": "당화혈색소",
    "age": "고연령",
    "dm_duration": "긴 유병기간",
    "bmi": "높은 BMI",
}


def _grad_feature_value(g: Graduate, feature: str):
    if feature == "hba1c":
        return g.hba1c_before
    if feature == "age":
        return g.age
    if feature == "dm_duration":
        return (g.dm_duration_months / 12.0) if g.dm_duration_months is not None else None
    if feature == "bmi":
        return g.init_bmi
    return None


def _case_payload(g: Graduate, card_type: str, match_label: str, match_detail: str, similarity: int) -> dict:
    _comp_b = json.loads(g.comp_before) if g.comp_before else None
    _comp_a = json.loads(g.comp_after) if g.comp_after else None
    _has_comp = bool(_comp_b and _comp_a)

    # 의료비·건강수명 — 합병증 위험도(6종) 개선 + 신장기능 + 나이 기반(services/outcome_model).
    #   이전에는 HbA1c 감소폭 하나만 써서, 신부전에서 회복한 71세(합병증 -42점)와 거의 변화
    #   없는 55세(-9.8점)가 감소폭이 같다는 이유로 완전히 동일한 값을 받았다.
    _outcome = treatment_outcome(
        _comp_b, _comp_a, g.age,
        egfr_before=g.egfr_before, egfr_after=g.egfr_after,
        hba1c_drop=g.hba1c_drop,
    )
    cost_saving = _outcome["cost_saving_man"]
    years_gain = _outcome["years_gain"]
    return {
        "card_type": card_type,
        "match_label": match_label,
        "match_detail": match_detail,
        "name": _mask_name(g.name),
        "sex": g.sex,
        "age": g.age,
        "goal": g.goal,
        "treatment_months": g.treatment_months,
        "dm_duration_months": g.dm_duration_months,
        "init_bmi": g.init_bmi,
        "dm_med_count": g.dm_med_count,
        "dm_med_count_after": g.dm_med_count_after,   # v2.3.5: '2개 → 0개' 감소 표시
        "hba1c_before": g.hba1c_before,
        "hba1c_after": g.hba1c_after,
        "hba1c_drop": g.hba1c_drop,
        "neuro_improve": g.neuro_improve,
        "similarity": similarity,
        # 증감 표시 (절감/연장 = 양수)
        "cost_saving_man": cost_saving,
        "healthy_years_gain": years_gain,
        # 'complications' = 합병증 위험도 기반, 'hba1c_only' = 합병증 데이터 없어 HbA1c 로 보조 추정
        "outcome_basis": _outcome["basis"],
        # 6/13 보강: C-peptide·eGFR·합병증 위험 전/후 (데이터 있으면 표시)
        "cpep_before": g.cpep_before,
        "cpep_after": g.cpep_after,
        "egfr_before": g.egfr_before,
        "egfr_after": g.egfr_after,
        "comp_before": _comp_b,
        "comp_after": _comp_a,
        "complications_pending": not _has_comp,
    }


@router.get("/case-comparison/{patient_id}")
def get_case_comparison(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # v2.3.0 (감사): 나이·유병기간을 앱 전체 단일 소스(services.derived, DOB 우선 현재값)로
    #   산출한다. 이전엔 저장 age/dm_duration 을 우선 사용해, 검사일 이후 시간이 지난
    #   오래된 행이 실제 현재 나이와 어긋난 취약 피처·졸업 사례로 매칭될 수 있었다.
    _pdict = _patient_to_dict(patient)
    hba1c = patient.hba1c
    age = _current_age_calc(_pdict) or patient.age
    dm_years = _current_dm_dur_calc(_pdict)
    if dm_years is None:
        dm_years = patient.dm_duration
    bmi = patient.bmi

    # 항목6(a): 통합 데이터 패널용 — 환자 본인의 BMI/C-peptide/HbA1c 시계열.
    measurements = (
        db.query(MeasurementHistory)
        .filter(MeasurementHistory.patient_id == patient_id)
        .order_by(MeasurementHistory.measured_at)
        .all()
    )
    timeline = [
        {
            "date": m.measured_at.isoformat() if m.measured_at else None,
            "bmi": m.bmi,
            "c_peptide": m.c_peptide,
            "hba1c": m.hba1c,
        }
        for m in measurements
        if (m.bmi is not None or m.c_peptide is not None or m.hba1c is not None)
    ]

    grads = db.query(Graduate).filter(
        Graduate.hba1c_before.isnot(None),
        Graduate.hba1c_after.isnot(None),
    ).all()
    total_loaded = db.query(Graduate).count()
    # 후보 = 치료기간 1년(12개월) 이내 + 실제 호전(HbA1c 감소>0) 졸업자만.
    #   (codex 검수: 악화 사례가 '유사/개선' 카드로 노출되거나 절감/연장이 양수로 둔갑하는 것 방지)
    candidates = [
        g for g in grads
        if g.treatment_months is not None and g.treatment_months <= TREATMENT_MONTHS_MAX
        and (g.hba1c_drop or 0) > 0
    ]

    if not candidates:
        note = (
            "졸업자 데이터가 없습니다. 설정 > '졸업자 데이터' 에서 엑셀을 업로드하세요."
            if total_loaded == 0 else
            "치료기간 1년 이내·호전(HbA1c 개선) 졸업자 후보가 없습니다."
        )
        return {"data": {
            "patient": {"name": patient.name, "hba1c": hba1c, "age": age},
            "graduate_count": total_loaded,
            "cases": [],
            "timeline": timeline,
            "data_note": note,
        }, "success": True}

    cases = []
    used_ids = set()

    # ── eGFR<60(신장 저하) 환자: 신장 회복 졸업자 사례를 미리 '예약' (카드①이 소진 못 하게) — 병원 6/13 ──
    reserved_kidney = None
    patient_egfr = patient.egfr
    if patient_egfr is not None and patient_egfr < 60:
        kpool = [
            g for g in candidates
            if g.egfr_before is not None and g.egfr_after is not None
            and g.egfr_before < 60 and g.egfr_after > g.egfr_before
        ]
        if kpool:
            reserved_kidney = max(kpool, key=lambda g: (g.egfr_after - g.egfr_before))
            used_ids.add(reserved_kidney.id)

    # ── 카드 ① 당화혈색소 유사 (예약된 신장사례 제외, 약간 더 높은 쪽 우선) ──
    if hba1c is not None:
        pool1 = [g for g in candidates if g.id not in used_ids]
        if pool1:
            higher = [g for g in pool1 if g.hba1c_before >= hba1c]
            if higher:
                g1 = min(higher, key=lambda g: g.hba1c_before - hba1c)
            else:
                g1 = min(pool1, key=lambda g: abs(g.hba1c_before - hba1c))
            diff = abs(g1.hba1c_before - hba1c)
            similarity = int(_clamp(round(100 - diff * 20), 60, 99))
            cases.append(_case_payload(
                g1, "hba1c_similar", "당화혈색소 유사 사례",
                f"치료 전 HbA1c {g1.hba1c_before}% (환자 {hba1c}%와 유사)", similarity,
            ))
            used_ids.add(g1.id)

    # ── 카드 ② 신장 회복(예약) 우선 노출, 없으면 최악 피쳐 ──
    kidney_case_done = False
    if reserved_kidney is not None:
        gk = reserved_kidney
        cases.append(_case_payload(
            gk, "kidney_recovery", "신장 기능 회복 사례",
            f"eGFR {gk.egfr_before}→{gk.egfr_after} (신장 기능 저하→회복)", 88,
        ))
        kidney_case_done = True

    # ── 카드 ② 최악 피쳐 유사 + 가장 극적 개선 (eGFR 신장사례를 못 채운 경우만) ──
    feature = _worst_feature(hba1c, age, dm_years, bmi)
    if not kidney_case_done and feature is not None:
        pv = {"hba1c": hba1c, "age": age, "dm_duration": dm_years, "bmi": bmi}[feature]
        pool = [g for g in candidates if g.id not in used_ids and _grad_feature_value(g, feature) is not None]
        if pool and pv is not None:
            pool.sort(key=lambda g: abs(_grad_feature_value(g, feature) - pv))
            near = pool[:max(5, len(pool) * 4 // 10)]
            g2 = max(near, key=lambda g: (g.hba1c_drop or 0))
            gv = _grad_feature_value(g2, feature)
            fl = _FEATURE_LABEL.get(feature, feature)
            cases.append(_case_payload(
                g2, "worst_feature", f"{fl} 유형 · 극적 개선 사례",
                f"환자의 가장 취약 지표({fl})와 유사하며 HbA1c {g2.hba1c_before}→{g2.hba1c_after}% (Δ{g2.hba1c_drop}) 개선",
                int(_clamp(round(90 - abs((gv if gv is not None else pv) - pv)), 60, 98)),
            ))
            used_ids.add(g2.id)

    # 후보가 적어 카드 2개를 못 채우면, 남은 후보 중 drop 최대로 계속 채움(codex: while 로 보강)
    while len(cases) < 2:
        rest = [g for g in candidates if g.id not in used_ids]
        if not rest:
            break
        g = max(rest, key=lambda g: (g.hba1c_drop or 0))
        cases.append(_case_payload(
            g, "dramatic", "극적 개선 사례",
            f"HbA1c {g.hba1c_before}→{g.hba1c_after}% (Δ{g.hba1c_drop}) 개선", 70,
        ))
        used_ids.add(g.id)

    return {"data": {
        "patient": {
            "name": patient.name, "hba1c": hba1c, "age": age,
            "worst_feature": _FEATURE_LABEL.get(feature) if feature else None,
        },
        "graduate_count": total_loaded,
        "cases": cases[:2],
        "timeline": timeline,
        # 합병증 위험 변화·eGFR 은 졸업자 raw 데이터셋(초진/졸업 실측)으로 산출된다.
        #   의료비·건강수명만 아직 HbA1c 개선폭 기반 추정치.
        "data_note": "합병증 위험 변화는 졸업자의 초진·졸업 실측값으로 산출한 예측 결과입니다. 의료비·건강수명은 합병증 위험도·신장기능·나이 변화를 반영한 추정치입니다.",
    }, "success": True}
