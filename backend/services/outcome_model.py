"""건강수명·의료비 산출의 단일 소스.

시나리오 화면(routers/scenario.py)과 유사사례 화면(routers/case_comparison.py)이
서로 다른 공식을 쓰던 것을 통일한다.

기존 문제:
  - 유사사례는 HbA1c 감소폭 하나만 사용 → 신부전에서 회복한 71세 환자(합병증 -42점)와
    거의 변화 없는 55세 환자(-9.8점)가 'HbA1c 감소폭 2.1' 이 같다는 이유로 완전히 동일한
    "의료비 -208만원 / +8세" 를 받았다.
  - 208명이 건강수명 12종으로만 갈려 해상도가 낮았다.

이 모듈은 '그 시점의 합병증 위험도(6종) + 나이 + 신장기능' 으로 상태를 평가하고,
치료 전/후 두 상태의 차이로 절감액·연장년수를 낸다. 시나리오가 쓰던 계수를 그대로 사용해
두 화면의 숫자가 같은 근거에서 나오도록 한다.

※ 의료비 '절대금액' 은 여전히 추정치다(계수가 임상 원가자료가 아님).
   병원 실제 진료비 데이터가 확보되면 COST_BASE/COST_SEVERITY_COEF 만 교체하면 된다.
"""
from __future__ import annotations

# 시나리오(routers/scenario.py)와 공유하는 계수 — 값 변경 시 양쪽 화면이 함께 움직인다.
SEVERITY_DIVISOR = 70.0     # 합병증 평균점수 → severity 정규화
SEVERITY_MIN = 0.15
SEVERITY_MAX = 1.0

LIFE_BASE = 82.0            # 기대 건강수명 기준선
LIFE_AGE_COEF = 10.0        # 나이 페널티 (age / 10)
LIFE_SEVERITY_COEF = 12.0   # 합병증 severity 페널티(년)

COST_BASE = 80.0            # 연간 의료비 기준선(만원)
COST_SEVERITY_COEF = 350.0  # 합병증 severity 가산(만원)

# 신장 기능은 투석 등으로 비용·수명 영향이 커서 별도 가산한다.
EGFR_DIALYSIS_RISK = 30.0   # 이 미만이면 말기신부전 위험 구간
EGFR_LOW = 60.0             # CKD 3기 경계
COST_EGFR_PENALTY = 220.0   # eGFR<30 일 때 연간 추가 비용(만원)
LIFE_EGFR_PENALTY = 6.0     # eGFR<30 일 때 건강수명 손실(년)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def severity_from_complications(scores) -> float:
    """6개 합병증 위험점수(dict 또는 list) → severity 계수 [0.15, 1.0].

    scenario._baseline_severity 와 동일 기준(mean / 70)을 쓴다.
    값이 없으면 보수적 중간값 0.4.
    """
    if not scores:
        return 0.4
    vals = list(scores.values()) if isinstance(scores, dict) else list(scores)
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return 0.4
    return _clamp(sum(vals) / len(vals) / SEVERITY_DIVISOR, SEVERITY_MIN, SEVERITY_MAX)


def _egfr_burden(egfr) -> tuple[float, float]:
    """eGFR → (추가 의료비 만원, 건강수명 손실 년). 낮을수록 크다."""
    if egfr is None:
        return 0.0, 0.0
    try:
        e = float(egfr)
    except (TypeError, ValueError):
        return 0.0, 0.0
    if e >= EGFR_LOW:
        return 0.0, 0.0
    # 60 → 0, 30 이하 → 최대. 사이는 선형.
    ratio = _clamp((EGFR_LOW - e) / (EGFR_LOW - EGFR_DIALYSIS_RISK), 0.0, 1.0)
    return COST_EGFR_PENALTY * ratio, LIFE_EGFR_PENALTY * ratio


def annual_cost(severity: float, egfr=None) -> float:
    """그 상태의 연간 의료비(만원) 추정."""
    cost_egfr, _ = _egfr_burden(egfr)
    return COST_BASE + severity * COST_SEVERITY_COEF + cost_egfr


def healthy_life_expectancy(severity: float, age, egfr=None, floor: bool = True) -> float:
    """그 상태를 유지할 때 도달하는 건강수명(세) 추정.

    floor=True 면 '현재 나이보다 낮은 건강수명' 모순을 막기 위해 age+1 하한을 적용한다.
    다만 전/후 차이(연장년수)를 구할 때는 floor=False 로 써야 한다 — 고령·중증 환자는
    전·후 값이 모두 하한에 눌려 실제 개선폭이 0 으로 사라지기 때문이다.
    (예: 71세 손О숙, 합병증 74→32 인데 56.9→69.4 가 둘 다 72 로 잘려 +0세가 됐다.)
    """
    try:
        a = float(age) if age is not None else 60.0
    except (TypeError, ValueError):
        a = 60.0
    _, life_egfr = _egfr_burden(egfr)
    life = LIFE_BASE - a / LIFE_AGE_COEF - severity * LIFE_SEVERITY_COEF - life_egfr
    return max(a + 1.0, life) if floor else life


def treatment_outcome(
    comp_before, comp_after, age,
    egfr_before=None, egfr_after=None,
    hba1c_drop=None,
) -> dict:
    """치료 전/후 상태 → 의료비 절감액·건강수명 연장년수.

    합병증 위험도(6종) 개선을 주 근거로 하고, 신장기능 회복과 HbA1c 개선을 보조로 반영한다.
    반환: {"cost_saving_man": int, "years_gain": int, "basis": str}
    """
    sev_b = severity_from_complications(comp_before)
    sev_a = severity_from_complications(comp_after)

    cost_b = annual_cost(sev_b, egfr_before)
    cost_a = annual_cost(sev_a, egfr_after)
    # 연장년수는 하한 없이 계산 — 하한을 걸면 고령·중증 환자의 개선폭이 잘려 0 이 된다.
    life_b = healthy_life_expectancy(sev_b, age, egfr_before, floor=False)
    life_a = healthy_life_expectancy(sev_a, age, egfr_after, floor=False)

    saving = cost_b - cost_a
    gain = life_a - life_b

    # 합병증 데이터가 없으면(구 wide 포맷 등) HbA1c 개선폭으로 보조 추정 — 기존 동작 유지.
    basis = "complications"
    if not comp_before or not comp_after:
        drop = max(0.0, float(hba1c_drop or 0.0))
        saving = 40.0 + drop * 80.0
        gain = 2.0 + drop * 3.0
        basis = "hba1c_only"

    return {
        "cost_saving_man": int(round(_clamp(saving, 10, 600))),
        "years_gain": int(round(_clamp(gain, 0, 20))),
        "basis": basis,
    }
