"""
시나리오 시뮬레이션 API
- 방치 시 vs 집중관리 시 비교
- 결정론적: 같은 입력이면 같은 출력. 슬라이더와 연속적으로 부드럽게 반응.
"""
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db, Patient
from models.schemas import ScenarioRequest
from services.derived import current_age as _current_age_calc
from services.derived import current_dm_duration as _current_dm_dur_calc
from ml.predictor import (
    predict_with_simulation,
    predict_all,
    classify_disease_risk,
    clinical_floor_levels,
    get_disease_threshold,
    get_disease_thresholds,
    CPEP_T1DM_SUSPECT,
)

router = APIRouter(prefix="/api/v1", tags=["scenario"])

# 병원 프로그램은 혈당 관리 궤적만 다루므로 시나리오 계산에서는 혈압/LDL floor 를 제외한다.
# 대시보드·/predict 경로는 predictor 의 기본값(1~7)을 그대로 사용한다.
SCENARIO_CLINICAL_FLOOR_RULES = frozenset({1, 2, 3, 4, 5})
SCENARIO_EXCLUDED_FLOOR_RULES = (6, 7)
SCENARIO_FLOOR_POLICY_NOTE = (
    "이 분석은 혈당 관리 기준이며, 지질·혈압 등 별도 위험요인은 "
    "대시보드에서 확인해 주세요."
)


# ── 유틸 ──

def _patient_to_dict(p: Patient) -> dict:
    return {c.name: getattr(p, c.name) for c in p.__table__.columns}


def _level(score, disease_key=None, age=None):
    # v2.1.9 (감사 — 등급 경계 통일): 30/60 고정 대신 질환별 모델 threshold 사용.
    # disease_key 없으면(legacy) 보수적으로 중위험.
    if score is None:
        return "중위험"
    if disease_key is None:
        if score >= 60:
            return "고위험"
        if score >= 30:
            return "중위험"
        return "저위험"
    return classify_disease_risk(score, disease_key, age=age) or "저위험"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _pf(v, default):
    """pdict 값 안전 float (None/비숫자 → default)."""
    return v if isinstance(v, (int, float)) else default


def _stable_offset(seed_key: str, lo: float, hi: float) -> float:
    """환자+질환 조합별 고정 오프셋. 슬라이더가 움직여도 변하지 않음."""
    h = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16)
    frac = (h % 10000) / 10000.0  # 0.0 ~ 1.0
    return lo + frac * (hi - lo)


# ── v2.2.2 (F2) — 임상 안전망 등급을 시나리오에 일관 반영하기 위한 유틸 ──
# predict_all 의 level floor 는 score 를 바꾸지 않으므로, 시나리오가 raw score 를
# 재분류할 때 선택된 정책의 floor 가 사라지지 않도록 아래 유틸로 level/display 를 맞춘다.
# 대시보드는 1~7, 시나리오는 1~5를 사용하므로 Rule 6·7에 따른 차이는 의도된 정책 차이다.
_LEVEL_RANK = {"저위험": 0, "중위험": 1, "고위험": 2}


def _max_level(a, b):
    """더 위험한(상위) 등급 반환. None/빈값은 무시. 강등 절대 없음."""
    if not a:
        return b
    if not b:
        return a
    return a if _LEVEL_RANK.get(a, 0) >= _LEVEL_RANK.get(b, 0) else b


def _score_for_level(score, level, disease_key, age):
    """display 점수를 목표 등급(level) 밴드 안으로 끌어올린다 (강등 없음).

    classify_disease_risk 와 동일 경계를 사용해 배지(level)와 진행 바(score)가
    어긋나지 않게 한다. 임상 안전망으로 등급이 승격됐는데 raw 점수가 낮으면
    "고위험인데 바는 짧다" 는 모순이 생기므로, 점수도 해당 밴드로 올린다.

    v2.2.2 (이질감 개선): 6개가 모두 고위험으로 고정될 때 raw 가 전부 60 미만이면 바가 다
    60 으로 똑같아진다. 고위험 밴드 안에서 raw 점수를 비례 반영(base + score×0.4)해 ML 상대
    위험 차이를 살린다 (모두 60 이상 = 고위험 유지). predictor._floor_band_score 와 동일 식.
      - 고위험: display = max(score, base + score×0.4)  (base = max(60, threshold)), 99 상한
      - 중위험: threshold ≤ display < 60
      - 저위험: 변경 없음
    """
    if level == "고위험":
        base = max(60.0, get_disease_threshold(disease_key, age=age) or 60.0)
        return round(_clamp(max(score, base + score * 0.4), 1, 99), 1)
    if level == "중위험":
        th = get_disease_threshold(disease_key, age=age) or 30.0
        return round(_clamp(min(max(score, th), 59.9), 1, 99), 1)
    return round(_clamp(score, 1, 99), 1)


# v2.1.7 — 신규 3개 패키지 모델 (neuropathy/dementia/cerebrovascular) 연동 완료.
# PENDING 세트 비움 → neglect/intensive 모두 ML 예측 사용.
# AVAILABLE 에 6개 모두 추가 → fold_change 등 정량 비교에 포함.
PENDING_MODELS = set()
AVAILABLE_MODELS = {"kidney", "retina", "cardio", "neuro", "dementia", "cerebro"}


# ── 전조증상 사전 (질환별 + HIGH/MEDIUM/LOW 등급) ──
# 의료진 검토본 v2.0 — 사용자 지정 우선순위 (3=HIGH, 2=MEDIUM, 1=LOW)
SYMPTOM_BANK: dict[str, dict[str, list[str]]] = {
    "retina": {
        "HIGH":   ["사물왜곡(변시증)", "시야결손"],
        "MEDIUM": ["시력저하", "광시증", "눈물"],
        "LOW":    ["침침함", "뻑뻑함", "충혈", "비문증"],
    },
    "kidney": {
        "HIGH":   ["거품뇨(지속적)", "단백뇨(검사상)", "전신부종"],
        "MEDIUM": ["거품뇨(아침 첫 소변만)"],
        "LOW":    ["소변량 변화", "피로감", "피부 가려움", "야간뇨"],
    },
    "cardio": {
        "HIGH":   ["가슴 압박감(흉통)", "호흡곤란"],
        "MEDIUM": ["식은땀", "두근거림", "방사통"],
        "LOW":    [],  # 의료진 추가 대기
    },
    # 뇌혈관 / 치매 / 신경병증: 추후 추가 (현재 SYMPTOM_BANK 미포함)
}


def _surface_symptoms_for(disease_key: str, level: str | None, max_items: int = 3) -> list[dict]:
    """
    합병증 점수 등급에 따라 노출할 전조증상 목록 산출.
      - 고위험 → HIGH 우선 + MEDIUM 보조 (LOW 는 노출 안 함, 시급성 부각)
      - 중위험 → MEDIUM 우선 + LOW 보조
      - 저위험 → LOW 만
      - 등급 없음/준비 중 → 빈 리스트
    질환 3개 모두 고위험이어도 페이지가 너무 길어지지 않도록 질환당 최대 max_items 개로 제한.
    각 항목은 {text, level} 딕셔너리.
    """
    bank = SYMPTOM_BANK.get(disease_key)
    if not bank or not level:
        return []

    if level == "고위험":
        order = ["HIGH", "MEDIUM"]
    elif level == "중위험":
        order = ["MEDIUM", "LOW"]
    else:  # 저위험
        order = ["LOW"]

    out: list[dict] = []
    for tier in order:
        for text in bank.get(tier, []):
            if len(out) >= max_items:
                break
            out.append({"text": text, "level": tier})
        if len(out) >= max_items:
            break
    return out


def _resolution_message(disease_key: str, level: str | None) -> str | None:
    """
    집중관리 6개월 후, 방치 시 노출되었던 전조증상이 어떻게 해결되는지 한 줄 메시지.
    프론트는 방치 박스의 질환별 증상에 대응하는 회복 카드로 사용.
    """
    if not level:
        return None
    msgs = {
        "retina": {
            "고위험": "사물 왜곡 · 시야 결손이 더 진행되지 않도록 안저 변화 안정화",
            "중위험": "광시증과 시력저하가 줄어들고 안구 피로감이 완화",
            "저위험": "침침함 · 비문증이 가벼워지고 일상 시야가 또렷해짐",
        },
        "kidney": {
            "고위험": "거품뇨와 부종이 줄어들고 단백뇨 수치가 호전",
            "중위험": "아침 거품뇨가 사라지고 하루 종일 컨디션이 안정",
            "저위험": "야간뇨 빈도가 줄고 피부 가려움 · 피로감이 가벼워짐",
        },
        "cardio": {
            "고위험": "운동 시 흉통 · 호흡곤란이 줄어 계단 오르기가 수월",
            "중위험": "식은땀 · 두근거림 · 어깨 방사통 빈도가 감소",
            "저위험": "심혈관 부담이 안정 단계로 회복",
        },
    }
    return msgs.get(disease_key, {}).get(level)


def _pending_reference_score(
    patient_id: int,
    disease_key: str,
    patient: Patient,
    hba1c: float | None = None,
    c_peptide: float | None = None,
) -> float:
    """
    미구현 모델의 참고 점수 (라이다 차트 시각 균형용).

    v2.0.x — 슬라이더에 **약하게** 반응하도록 개선:
      - HbA1c 가 높을수록, C-peptide 가 낮을수록 점수 ↑
      - 환자 고정 특성(age/sbp/dm_dur) + 슬라이더 영향 결합
      - 최대 50 점으로 제한 (실제 ML 모델보다 우위에 서지 않게)
      - 프론트는 여전히 '준비 중' 배지로 ML 미구현임을 명시
    """
    age = patient.age or 60
    sbp = patient.sbp or 130
    dm_dur = patient.dm_duration or 5

    # 슬라이더 기여 — HbA1c (+), C-peptide (−)
    hba1c_v = hba1c if hba1c is not None else (patient.hba1c or 7.0)
    cpep_v  = c_peptide if c_peptide is not None else (patient.c_peptide or 2.0)
    slider_term = (hba1c_v - 6.5) * 3.5 + (2.5 - cpep_v) * 4.0

    if disease_key == "neuro":
        base = 12 + dm_dur * 1.2
    elif disease_key == "cerebro":
        base = 12 + (sbp - 120) * 0.35 + (age - 55) * 0.25
    elif disease_key == "dementia":
        base = 12 + (age - 55) * 0.55
    else:
        base = 12

    offset = _stable_offset(f"{patient_id}:{disease_key}", -3, 3)
    return round(_clamp(base + slider_term + offset, 8, 50), 1)


def _slider_sensitivity_boost(
    base_hba1c: float,
    base_cpep: float,
    cur_hba1c: float,
    cur_cpep: float,
) -> float:
    """
    환자 baseline 대비 슬라이더 변화량을 기반으로 한 가시성 보정값.
    ML 모델의 raw 점수에 더해 라이다 변화를 강조한다.
      - HbA1c +1% → +4 점
      - C-peptide -1 ng/mL → +6 점 (인슐린 분비능 감소가 더 무겁게)
    완전히 동일하면 0.
    """
    return (cur_hba1c - base_hba1c) * 4.0 + (base_cpep - cur_cpep) * 6.0


def _baseline_severity(radar: dict) -> tuple[float, float]:
    """
    환자의 현재 합병증 평균 점수와 그 정규화값(severity 계수)을 반환.

    반환: (mean_score, severity)
      - mean_score: 0~99 원점수. _classify_risk 와 동일 컷오프(< 30 저위험) 비교용.
      - severity:   페널티 계수. [0.15, 1.0] 으로 정규화 (mean/70).
    """
    avail = [v for k, v in radar.items() if k in AVAILABLE_MODELS and v is not None]
    if not avail:
        return 30.0, 0.4  # ML 점수 없으면 보수적 중간값
    mean = sum(avail) / len(avail)
    return mean, _clamp(mean / 70.0, 0.15, 1.0)


def _slider_drift(base_hba1c: float, base_cpep: float, cur_hba1c: float, cur_cpep: float) -> tuple[float, float]:
    """
    환자 baseline 대비 슬라이더가 나쁜 방향/좋은 방향으로 얼마나 움직였는지.
    반환: (worse_drift, better_drift) 둘 다 ≥ 0.
      - HbA1c 가 baseline 보다 +1% → worse +1.0
      - C-peptide 가 baseline 보다 -0.5 → worse +0.5
      - 반대로 움직이면 better 쪽에 누적
    """
    worse = max(0.0, cur_hba1c - base_hba1c) + max(0.0, base_cpep - cur_cpep)
    better = max(0.0, base_hba1c - cur_hba1c) + max(0.0, cur_cpep - base_cpep)
    return worse, better


def _worsen(score: float, baseline_sev: float, drift_worse: float) -> float:
    """
    방치/현 수치 유지 시 합병증 점수.
    저위험 + 슬라이더 그대로 → 거의 변하지 않음 (과장된 위협 방지).
    고위험 + 슬라이더 악화 → 큰 폭으로 증가.
    """
    delta = baseline_sev * 8.0 + drift_worse * 5.0
    return round(_clamp(score + delta, 1, 95), 1)


def _improve(score: float, baseline_sev: float, drift_better: float) -> float:
    """
    집중관리 시 합병증 점수.
    슬라이더 개선폭이 클수록, 환자 baseline 위험이 클수록 더 큰 개선.
    저위험 환자가 슬라이더 그대로면 작은 개선만 (현 상태가 이미 좋음).
    """
    delta = baseline_sev * 6.0 + drift_better * 8.0
    return round(_clamp(score - delta, 2, 90), 1)


# ── 엔드포인트 ──

def build_scenario_payload(patient, pdict, age, sim_hba1c, sim_cpep, base_hba1c, base_cpep):
    """시나리오 3종(현재유지/집중관리/졸업) 계산 — /scenario/simulate 와 통합 리포트가 공유.

    - pdict              : baseline 데이터 dict (현재 환자값 또는 초진 스냅샷)
    - sim_hba1c/sim_cpep : 시뮬레이션(슬라이더) 값. 초진 리포트는 baseline=sim 이라 drift 0.
    - base_hba1c/base_cpep : 슬라이더 drift 판정 기준값(현재값).
    반환: 응답 data dict ({"insufficient":True,...} 또는 전체 시나리오 payload).
    """
    hba1c_current = base_hba1c
    cpep_current = base_cpep

    # ── ML 예측 (3개 로드된 모델만 실제 proba) ──
    # predict_with_simulation 이 이미 sim_cpep / sim_hba1c 를 features 에 반영해서
    # 예측하므로 ML 모델은 슬라이더 효과를 자체적으로 흡수한다.
    current_pred = predict_with_simulation(
        pdict,
        sim_cpep,
        sim_hba1c,
        enabled_rules=SCENARIO_CLINICAL_FLOOR_RULES,
    )

    # v2.2.8 (병원 정책): 필수 검사(지질·Cr·혈압·키·몸무게·나이·성별 등)가 없으면
    #   시나리오를 추정으로 지어내지 않고 '데이터 부족'을 반환한다. (predict_all 게이트 결과 확인)
    if current_pred and all(v.get("risk_source") == "insufficient_data" for v in current_pred.values()):
        missing = next((v.get("missing_required") for v in current_pred.values() if v.get("missing_required")), [])
        return {
            "insufficient": True,
            "missing_required": missing,
            "meta": {
                "excluded_floor_rules": list(SCENARIO_EXCLUDED_FLOOR_RULES),
                "floor_policy_note": SCENARIO_FLOOR_POLICY_NOTE,
            },
        }

    # ── 슬라이더 가시성 보정 ──
    # v2.1.3 (Codex 리뷰 반영): 실 ML 점수에는 sensitivity 가산 적용 X.
    # ML 모델이 이미 슬라이더 값을 입력으로 받아 점수를 산출했기 때문에 추가 가산은 이중 반영.
    # sensitivity 는 ML 미구현 모델 (신경병증·치매·뇌혈관) 의 휴리스틱 참고값에만 적용.
    sensitivity = _slider_sensitivity_boost(
        base_hba1c=hba1c_current,
        base_cpep=cpep_current,
        cur_hba1c=sim_hba1c,
        cur_cpep=sim_cpep,
    )

    # ── Radar 데이터 (6개 합병증 점수) ──
    name_map = {
        "neuropathy": "neuro",
        "retinopathy": "retina",
        "kidney_disease": "kidney",
        "cardiovascular": "cardio",
        "cerebrovascular": "cerebro",
        "dementia": "dementia",
    }

    radar = {}
    current_floor = {}  # v2.2.2 (F2): 시나리오 1~5 정책이 적용된 current_pred level
    heuristic_keys = set()  # v2.3.0 (감사): ML 예측 실패로 휴리스틱 참고값을 쓴 합병증
    for full_name, short_name in name_map.items():
        pred = current_pred.get(full_name, {})
        score = pred.get("score")
        if score is None:
            # score is None 경로:
            #  - 정상 배포본(CI smoke test 통과)에서는 6개 모델 항상 로드되어 도달하지 않음.
            #  - 모델 번들이 깨진 비정상 환경에서만 도달 → 휴리스틱 참고값으로 시각화.
            # v2.3.0 (감사): 이전엔 휴리스틱 점수가 정상 ML 결과처럼 응답에 섞여
            #   등급·추천 프로그램에 쓰였다 → heuristic_keys 로 추적해
            #   (1) radar_display 에 available=False/source 명시,
            #   (2) 시나리오 강도(severity)·추천 프로그램 계산에서 제외한다.
            score = _pending_reference_score(
                patient.id, short_name, patient,
                hba1c=sim_hba1c, c_peptide=sim_cpep,
            )
            # 미구현 모델은 ML 예측이 없으므로 sensitivity 로 슬라이더 변화 시각화
            score = round(_clamp(score + sensitivity, 1, 99), 1)
            # 모델 unavailable 이어도 Rule 1/5 강제 고위험은 예측과 독립된 임상 안전망이다.
            current_floor[short_name] = pred.get("level")
            heuristic_keys.add(short_name)
        else:
            # 실 ML 점수 그대로 사용 (predict_with_simulation 이 이미 슬라이더 반영)
            score = round(_clamp(score, 1, 99), 1)
            # v2.2.2 (F2): 선택된 시나리오 정책의 floored level 보관
            current_floor[short_name] = pred.get("level")
        radar[short_name] = score

    # v2.2.2 (F2): 응답용 radar 는 선택된 임상 안전망 등급을 반영한다.
    #   내부 시뮬레이션 계산(baseline_severity / worsen / improve)은 raw radar 를 그대로 사용.
    # v2.2.2 (codex R3 blocker): 숫자만 보내면 프론트가 30/60 fallback 으로 재분류해
    #   모델 threshold(예: retina 19.49) 기준 중위험을 저위험으로 과소표시함 → {score,display_score,level}
    #   객체로 보내 RadarChart 가 backend level 을 그대로 쓰게 한다.
    radar_display = {}
    for short_key, raw_score in radar.items():
        disp_level = _max_level(_level(raw_score, short_key, age), current_floor.get(short_key))
        radar_display[short_key] = {
            "score": raw_score,
            "display_score": _score_for_level(raw_score, disp_level, short_key, age),
            "level": disp_level,
            # v2.3.0 (감사): 모델 실패 시 휴리스틱 참고값임을 응답에 명시.
            "available": short_key not in heuristic_keys,
            "source": "heuristic" if short_key in heuristic_keys else "ml",
        }

    # ── v2.1 baseline-aware 시뮬레이션 ──
    # 환자의 현 합병증 평균 점수 + 슬라이더 변화량(악화/개선 방향) 두 축으로
    # 방치/집중관리 시나리오의 강도를 결정. 저위험 환자에게 과장된 경고가 나가지 않게.
    # v2.3.0 (감사): 임상 안전망으로 승격된 등급이 시나리오 강도·라벨에서 무시되어
    #   "전 항목 강제 고위험인데 '현재 수치 유지/안정 단계'·의료비 +5%" 로 표시되던 문제 —
    #   raw 점수 대신 안전망 반영된 display_score 로 severity 를 계산하고,
    #   고위험 합병증이 하나라도 있으면 'maintain' 라벨을 쓰지 않는다.
    #   (휴리스틱 참고값은 severity 계산에서 제외)
    _severity_scores = {
        k: v["display_score"] for k, v in radar_display.items() if k not in heuristic_keys
    }
    mean_score, baseline_sev = _baseline_severity(_severity_scores)
    drift_worse, drift_better = _slider_drift(
        hba1c_current, cpep_current, sim_hba1c, sim_cpep
    )
    # 슬라이더 변화 임계값 — HbA1c 0.5% 또는 C-peptide 0.5 ng/mL 정도 움직였을 때만 "변경됨" 판정.
    # 사용자가 무심코 0.1~0.3 정도 만지는 건 baseline 으로 간주해서 톤 유지.
    slider_changed = (drift_worse + drift_better) > 0.5
    # 합병증 평균 점수가 저위험 컷오프(< 30) 미만이고 슬라이더가 크게 안 움직였으면
    # "방치" 대신 "현재 수치 유지" 라벨 사용. _classify_risk 와 동일 컷오프로 정합성 유지.
    _any_high_now = any(
        v.get("level") == "고위험" for k, v in radar_display.items() if k not in heuristic_keys
    )
    neglect_label_mode = (
        "maintain" if (mean_score < 30 and not slider_changed and not _any_high_now) else "neglect"
    )

    # ── 졸업(완전 회복) 고정 anchor + 집중관리 졸업 수렴 계수 ──
    # v2.2.2 (사용자 요청): 졸업 박스의 예상 건강수명·의료비는 슬라이더 영향 없이 고정.
    #   동시에, 슬라이더(혈당)+환자의 비정상 동반수치가 졸업 이상치에 가까울수록(conv→1)
    #   '집중관리 시' 수명·의료비도 졸업값에 수렴한다. 다른 수치가 졸업 기준과 다르면 격차 유지.
    GRADUATION_VALUES = {
        "hba1c": 5.6, "c_peptide": 1.3, "fbg": 90.0,
        "sbp": 120.0, "dbp": 80.0, "bmi": 22.0,
    }
    grad_life = max(62, age + 5, int(82 - age / 10 + 10))   # 고정 최선 (age 만 의존)
    grad_cost = int(_clamp(40 + age * 0.2, 40, 55))         # 고정 최저 (age 만 의존)

    # 졸업 이상치 대비 이탈도 — 혈당(슬라이더)이 주요인, 동반수치는 '비정상 구간'만 가산.
    _sbp = _pf(pdict.get("sbp"), 120.0)
    _dbp = _pf(pdict.get("dbp"), 80.0)
    _bmi = _pf(pdict.get("bmi"), 22.0)
    managed_gap = (
        abs(sim_hba1c - GRADUATION_VALUES["hba1c"]) * 0.7
        + abs(sim_cpep - GRADUATION_VALUES["c_peptide"]) * 0.4
        + max(0.0, _sbp - 130.0) * 0.04       # 수축기 130 초과분만 (정상 여유 확보)
        + max(0.0, _dbp - 85.0) * 0.04        # 이완기 85 초과분만
        + max(0.0, _bmi - 25.0) * 0.06        # 비만(>25)만
        + max(0.0, 18.5 - _bmi) * 0.04        # 저체중(<18.5)만
    )
    # gap 0 → conv 1 (집중관리가 졸업에 완전 수렴), gap ≥ 2 → conv 0 (기존 휴리스틱)
    grad_conv = _clamp(1.0 - managed_gap / 2.0, 0.0, 1.0)

    # ── 방치/현재유지 시 시나리오 ──
    neglect_complications = {}
    for short in radar:
        if short in PENDING_MODELS:
            neglect_complications[short] = {"level": "분석 진행 중", "score": None}
        else:
            worsened = _worsen(radar[short], baseline_sev, drift_worse)
            # v2.2.2 (F2): 방치/현재유지는 환자 현재(슬라이더) 수치이므로 시나리오 정책의
            #   임상 안전망 등급을 최소 보장한다. 재분류 등급 vs floored level 중 더 위험한 쪽 채택,
            #   점수도 해당 등급 밴드로 맞춰 배지/바 정합성 유지.
            level = _max_level(_level(worsened, short, age), current_floor.get(short))
            neglect_complications[short] = {
                "level": level,
                "score": _score_for_level(worsened, level, short, age),
            }

    # 건강수명 감소 — baseline severity + 악화 방향 drift 가 클수록 큼.
    # 저위험 + 슬라이더 그대로 → 1년 미만 (사실상 변화 없음).
    life_hit = _clamp(baseline_sev * 12.0 + drift_worse * 3.0, 0.5, 18.0)

    # 의료비 절대치 — 환자 baseline 위험에 비례. 슬라이더 악화도 반영.
    cost_base = int(80 + baseline_sev * 350 + drift_worse * 100)
    # 의료비 증가율 — 저위험 환자는 +5% 정도, 고위험 + 큰 악화 → +130%
    cost_increase_pct = int(_clamp(baseline_sev * (15 + drift_worse * 50), 5, 130))
    # v2.3.0 (감사): 방치 절대액·증가율과 집중관리 절대액·감소율이 서로 독립 계산되어
    #   역산하면 '현재 의료비'가 두 값으로 갈라지던 모순 수정 — 단일 현재 의료비를
    #   방치액/증가율에서 도출하고, 집중관리 감소율은 같은 기준으로 실계산한다.
    neglect_cost = max(120, cost_base + int(baseline_sev * 200))
    current_cost = max(60, int(round(neglect_cost / (1 + cost_increase_pct / 100.0))))

    # 인슐린 시작 확률 — 저위험 환자는 거의 0, 고위험 + 악화 → 90%
    insulin_prob = int(_clamp(baseline_sev * (15 + drift_worse * 60), 2, 90))

    # 당뇨약 개수 추정
    drug_before = 1 if (sim_hba1c < 7.5 and baseline_sev < 0.5) else 2
    drug_after = drug_before + int(_clamp(baseline_sev * 1.5 + drift_worse * 1.5, 0, 4))
    drug_after = min(5, drug_after)

    # ── 질환별 전조증상 (방치 시 worsened 등급 기반) ──
    # 각 질환의 worsened 점수가 어느 등급(고/중/저위험)에 속하는지에 따라
    # 노출할 증상 우선순위(HIGH/MEDIUM/LOW) 결정. 프론트는 등급 배지로 표시.
    neglect_symptoms = {}
    for short_key in SYMPTOM_BANK.keys():
        comp = neglect_complications.get(short_key, {})
        items = _surface_symptoms_for(short_key, comp.get("level"))
        if items:
            neglect_symptoms[short_key] = items

    # 건강수명 — 환자 현재 나이보다 낮아지면 모순이므로 age + 1 이상 보장.
    # 저위험 + 변화 없음일 때는 거의 정상 기대수명 (life_hit ~0.5) 으로 합리적인 결과.
    neglect_life_raw = int(82 - (age / 10) - life_hit)
    neglect_life = max(50, age + 1, neglect_life_raw)

    neglect = {
        "life_expectancy": neglect_life,
        "annual_cost_man": neglect_cost,
        "annual_cost_current_man": current_cost,  # v2.3.0: 단일 '현재 의료비' 기준 노출
        "cost_increase_pct": cost_increase_pct,
        "drug_count_before": drug_before,
        "drug_count_after": drug_after,
        "insulin_probability": insulin_prob,
        "complications": neglect_complications,
        # v2.1 — 저위험 환자에게 "방치" 대신 "현재 수치 유지" 라벨 사용.
        "label_mode": neglect_label_mode,  # 'maintain' | 'neglect'
        # v2.0.3: 질환별 grouped + leveled. 프론트는 grouped 우선 렌더, fallback 으로 'symptoms_legacy' 사용.
        "symptoms_by_disease": neglect_symptoms,
        # 하위호환: 구 프론트 빌드는 flat list 가정. 일단 빈 리스트로 두지 않고 의의 보존.
        "symptoms": [
            f"[{item['level']}] {item['text']}"
            for items in neglect_symptoms.values()
            for item in items
        ],
    }

    # ── 집중관리 시 시나리오 (baseline-aware) ──
    # v2.2.2 (H5/안전): 개선된 수치를 먼저 산출해 임상 안전망을 재평가한다.
    # v2.2.8 (6/8 피드백): 집중관리 목표 = HbA1c 1.8%P 감소(혈당개선탕 근거). 단 5.0% 미만으로는
    #   내려가지 않게(=4%대 절대 금지) 하한 5.0, 현재값보다 높아지지 않게 상한 clamp.
    hba1c_after = round(min(sim_hba1c, max(5.0, sim_hba1c - 1.84)), 1)

    # v2.2.8 (6/8 피드백): 집중관리 시 C-peptide — 오리지널이 정상 하한 미만이면 +0.6 증가(췌장 기능 회복),
    #   이미 정상역이면 그대로 유지(더 올리지 않음). 상한 3.5.
    #   정상 하한 = 임상 floor(Rule 3, CPEP_T1DM_SUSPECT=1.0 ng/mL = 병원 참고범위 하한)와 동기화.
    #   → floor 미만 환자만 boost 대상이 되고, boost 후 floor 를 넘겨 개선이 등급에 반영되게 한다.
    NORMAL_CPEP_LO, NORMAL_CPEP_HI = CPEP_T1DM_SUSPECT, 3.5
    if sim_cpep < NORMAL_CPEP_LO:
        cpep_after = min(NORMAL_CPEP_HI, sim_cpep + 0.64)
    else:
        cpep_after = sim_cpep
    cpep_after = round(cpep_after, 2)

    # v2.2.2 (H5/안전): 집중관리도 개선된 수치(hba1c_after·cpep_after)로 임상 안전망 재평가.
    #   수치가 정상화되면 floor 자동 해제(개선 표시), 아직 위험역(예: hba1c_after≥11/≥9)이면
    #   등급 유지 → 의학적 과소표시 방지. egfr/혈압 등은 슬라이더로 안 바뀌므로 patient 값 유지.
    intensive_floor = {
        name_map[full]: lvl
        for full, lvl in clinical_floor_levels(
            # v2.2.2 (codex R2): 안전망이 stale dm_duration/age 를 읽지 않게 현재값 주입.
            {**pdict, "hba1c": hba1c_after, "c_peptide": cpep_after,
             "age": age, "dm_duration": _current_dm_dur_calc(pdict)},
            list(name_map.keys()),
            enabled_rules=SCENARIO_CLINICAL_FLOOR_RULES,
        ).items()
    }

    intensive_complications = {}
    for short in radar:
        if short in PENDING_MODELS:
            intensive_complications[short] = {"level": "분석 진행 중", "score": None}
        else:
            improved = _improve(radar[short], baseline_sev, drift_better)
            level = _max_level(_level(improved, short, age), intensive_floor.get(short))
            intensive_complications[short] = {
                "level": level,
                "score": _score_for_level(improved, level, short, age),
            }

    # 건강수명 회복 — 저위험 환자는 작은 회복(이미 건강), 고위험 환자는 큰 회복.
    life_gain = _clamp(baseline_sev * 5.0 + drift_better * 3.0, 1.0, 8.0)
    cost_after = int(_clamp(cost_base * 0.4, 60, 400))
    # v2.2.2 (졸업 수렴): 프로필이 졸업 이상치에 가까울수록(grad_conv→1) 졸업 의료비로 당김.
    #   grad_cost ≤ cost_after 이므로 의료비는 내려가고, 항상 grad_cost ≤ 집중 ≤ 방치 유지.
    cost_after = int(round(cost_after + (grad_cost - cost_after) * grad_conv))
    # v2.3.0 (감사): 감소율을 별도 휴리스틱으로 지어내지 않고 단일 '현재 의료비' 기준으로
    #   실계산 — 화면의 절대액·비율이 항상 서로 성립한다. (집중관리 ≤ 현재의 95% 보장)
    cost_after = max(grad_cost, min(cost_after, int(current_cost * 0.95)))
    cost_decrease_pct = int(_clamp(round((current_cost - cost_after) * 100.0 / current_cost), 1, 99))

    # 집중관리 건강수명 — age + 3 이상, 방치보다 +2 이상.
    intensive_life_raw = int(82 - (age / 10) + life_gain)
    intensive_life = max(60, age + 3, neglect_life + 2, intensive_life_raw)
    # v2.2.2 (졸업 수렴): 프로필이 졸업 이상치에 가까울수록(grad_conv→1) 졸업 수명으로 당김.
    #   grad_life ≥ intensive 이므로 수명은 올라가고, 항상 방치 ≤ 집중 ≤ grad_life 유지.
    intensive_life = int(round(intensive_life + (grad_life - intensive_life) * grad_conv))

    # ── 집중관리 시 회복 메시지 (방치 측 전조증상에 1:1 대응) ──
    # 방치 박스에 노출된 각 질환의 worsened 등급을 기준으로 "어떻게 해결되는지" 한 줄.
    symptoms_resolved = {}
    for short_key, items in neglect_symptoms.items():
        if not items:
            continue
        comp = neglect_complications.get(short_key, {})
        msg = _resolution_message(short_key, comp.get("level"))
        if msg:
            symptoms_resolved[short_key] = msg

    intensive = {
        "life_expectancy": intensive_life,
        "annual_cost_man": cost_after,
        "annual_cost_current_man": current_cost,  # v2.3.0: 방치 카드와 동일한 '현재 의료비' 기준
        "cost_decrease_pct": cost_decrease_pct,
        "hba1c_before": round(sim_hba1c, 1),
        "hba1c_after": round(hba1c_after, 1),
        "cpeptide_before": round(sim_cpep, 2),
        "cpeptide_after": round(cpep_after, 2),
        "complications": intensive_complications,
        # v2.0.5 — 방치측 전조증상에 대응하는 질환별 회복 한 줄. 프론트가 우선 렌더링.
        "symptoms_resolved_by_disease": symptoms_resolved,
        # 하위호환: 일반 generic improvements (구 프론트 빌드용)
        "improvements": [
            "아침 기상 시 컨디션이 눈에 띄게 상쾌해짐",
            "식후 졸음 부담 없이 가볍게 견딤",
            "시야가 더 또렷해지고 안구 건조감 완화",
            "손발 저림 증상 완화 및 운동 능력 향상",
        ],
    }

    # ── 졸업시 시나리오 (표준 졸업값 고정, 슬라이더 영향 없음) ──
    # GRADUATION_VALUES / grad_life / grad_cost 는 위 '졸업 anchor' 블록에서 이미 정의됨.
    #   (원장 회신: C-peptide 1.3 = 정상 회복 기준, HbA1c 5.6% = 정상 상한)
    grad_patient = dict(pdict)
    grad_patient.update({
        "hba1c": GRADUATION_VALUES["hba1c"],
        "c_peptide": GRADUATION_VALUES["c_peptide"],
        "fbg": GRADUATION_VALUES["fbg"],
        "sbp": GRADUATION_VALUES["sbp"],
        "dbp": GRADUATION_VALUES["dbp"],
        "bmi": GRADUATION_VALUES["bmi"],
    })
    # v2.2.2 (F3 fbg 버그 수정): predict_with_simulation 은 내부에서 fbg 를 슬라이더
    #   HbA1c 기준으로 재추정해(v2.3.0: ADAG 스케일) GRADUATION_VALUES["fbg"]=90 을
    #   무효화한다. grad_patient 에 표준 졸업값(hba1c·c_peptide·fbg·sbp·dbp·bmi)이 모두
    #   들어있으므로 predict_all 로 직접 예측해 표준 fbg=90 을 보존한다.
    #   (HOMA 등 파생값은 c_peptide·fbg 로 재계산됨)
    grad_pred = predict_all(
        grad_patient,
        enabled_rules=SCENARIO_CLINICAL_FLOOR_RULES,
    )

    # codex(H2): 졸업 안전망은 'raw ML 등급'이 아니라 비가역 임상 floor(eGFR<45 Rule5 등)만
    #   반영해야 한다. pred["level"]은 ML 분류까지 포함하므로 floor 를 따로 계산한다.
    #   (안 그러면 raw ML 이 중위험이던 합병증이 floor_locked 로 오판돼 ×0.5 감쇠가 무효화됨)
    grad_floor = {
        name_map[full]: lvl
        for full, lvl in clinical_floor_levels(
            {**grad_patient, "age": age, "dm_duration": _current_dm_dur_calc(pdict)},
            list(name_map.keys()),
            enabled_rules=SCENARIO_CLINICAL_FLOOR_RULES,
        ).items()
    }

    grad_complications = {}
    grad_floor_locked = {}   # 비가역 안전망(eGFR<45 등)으로 등급이 잠긴 합병증
    for full_name, short_name in name_map.items():
        pred = grad_pred.get(full_name, {})
        # 표준 졸업값에도 남는 '비가역' 안전망(예: eGFR<45 Rule5)은 졸업이라도 존중.
        grad_floor_level = grad_floor.get(short_name)
        raw_score = pred.get("score")
        if raw_score is None:
            base = _pending_reference_score(
                patient.id, short_name, patient,
                hba1c=GRADUATION_VALUES["hba1c"],
                c_peptide=GRADUATION_VALUES["c_peptide"],
            )
            score = round(_clamp(base * 0.25, 2, 15), 1)
        else:
            # v2.2.8 (6/8 피드백): 졸업(완전 회복)은 집중관리보다 '확연히' 좋게 보여야 하므로
            #   표준값 ML 예측을 추가 감쇠(×0.5)해 시각적 대비를 키운다. (단조성·고정성은 유지)
            score = round(_clamp(raw_score * 0.5, 1, 99), 1)
        # 비가역 안전망이 자연 등급보다 위험하면 그 등급으로 잠금(floor_locked).
        natural_level = _level(score, short_name, age)
        level = _max_level(natural_level, grad_floor_level)
        grad_floor_locked[short_name] = (level != natural_level)
        grad_complications[short_name] = {
            "level": level,
            "score": _score_for_level(score, level, short_name, age),
        }

    # v2.2.8 단조성 + 확연한 대비: 졸업 ≤ 집중 ≤ 방치 보장하되, 졸업이 floor 로 잠긴 게 아니면
    #   집중을 졸업의 약 1.67배(=졸업이 집중의 60% 이하)로 끌어올려 '확연한 개선'이 보이게 한다.
    for short_name, grad_info in grad_complications.items():
        g = grad_info.get("score")
        if g is None:
            continue
        ic = intensive_complications.get(short_name, {})
        if ic.get("score") is not None:
            target = g if grad_floor_locked.get(short_name) else round(_clamp(g / 0.6, 1, 99), 1)
            if ic["score"] < target:
                lvl = _max_level(_level(target, short_name, age), intensive_floor.get(short_name))
                ic["level"] = lvl
                ic["score"] = _score_for_level(target, lvl, short_name, age)
        nc = neglect_complications.get(short_name, {})
        isc = ic.get("score")
        if nc.get("score") is not None and isc is not None and nc["score"] < isc:
            lvl = _max_level(_level(isc, short_name, age), current_floor.get(short_name))
            nc["level"] = lvl
            nc["score"] = _score_for_level(isc, lvl, short_name, age)

    # 단조성 하드 가드(병원 피드백): 모든 합병증에서 neglect >= intensive >= graduation 을
    #   점수·등급 양쪽에서 '최종' 강제한다. (임상 floor·level↔score 역변환으로 표시값이
    #   튀어 졸업>집중 / 집중>방치 역전이 종종 발생 → 후처리에서 확정 보정)
    for short_name in name_map.values():
        gc = grad_complications.get(short_name) or {}
        ic = intensive_complications.get(short_name) or {}
        nc = neglect_complications.get(short_name) or {}
        # intensive >= graduation
        if ic.get("score") is not None and gc.get("score") is not None:
            s = max(ic["score"], gc["score"])
            lv = _max_level(_max_level(ic.get("level"), gc.get("level")), _level(s, short_name, age))
            ic["score"] = _score_for_level(s, lv, short_name, age)
            ic["level"] = _max_level(lv, _level(ic["score"], short_name, age))
        # neglect >= intensive (갱신된 intensive 기준)
        if nc.get("score") is not None and ic.get("score") is not None:
            s = max(nc["score"], ic["score"])
            lv = _max_level(_max_level(nc.get("level"), ic.get("level")), _level(s, short_name, age))
            nc["score"] = _score_for_level(s, lv, short_name, age)
            nc["level"] = _max_level(lv, _level(nc["score"], short_name, age))

    # grad_life / grad_cost 는 위 '졸업 anchor' 블록에서 고정값으로 이미 산출됨(슬라이더 무관).
    delta_life = grad_life - neglect_life
    delta_cost = neglect["annual_cost_man"] - grad_cost
    delta_complications = {}
    for short_name, grad_info in grad_complications.items():
        neg_info = neglect_complications.get(short_name, {})
        if grad_info.get("score") is None or neg_info.get("score") is None:
            delta_complications[short_name] = None
        else:
            delta_complications[short_name] = round(neg_info["score"] - grad_info["score"], 1)

    graduation = {
        "life_expectancy": grad_life,
        "annual_cost_man": grad_cost,
        "complications": grad_complications,
        "standard_values": dict(GRADUATION_VALUES),
        "description": "표준 졸업값 기준 — 슬라이더 영향 없음",
        "delta_vs_neglect": {
            "life_expectancy": delta_life,
            "annual_cost_man": -delta_cost,
            "annual_cost_decrease": delta_cost,
            "complications": delta_complications,
        },
    }

    # 백분위 → 배수 표시용 fold change (현재 환자 ML 점수 기반)
    fold_change_by_disease = {}
    try:
        from services.percentile import compute_fold_change
        for full_name, short_name in name_map.items():
            pred = current_pred.get(full_name, {})
            score = pred.get("score")
            if score is not None:
                fc = compute_fold_change(full_name, age, score)
                if fc:
                    fold_change_by_disease[short_name] = fc
    except Exception:
        pass

    # ── 추천 프로그램 (실제 ML 예측이 있는 합병증 중 가장 높은 위험도 기반) ──
    # v2.3.0 (감사): 휴리스틱 참고값(모델 실패)은 추천 근거에서 제외.
    available_radar = {
        k: v for k, v in radar.items() if k in AVAILABLE_MODELS and k not in heuristic_keys
    }
    max_risk = max(available_radar, key=available_radar.get) if available_radar else "kidney"
    program_map = {
        "kidney": ("Kidney Shield", "신장 기능 보존을 위한 12주 집중 케어"),
        "retina": ("Vision Guard", "망막 건강 보호를 위한 8주 맞춤 프로그램"),
        "cardio": ("Heart Care Plus", "심혈관 위험 관리를 위한 12주 통합 케어"),
        "neuro": ("Neuropathy Guard", "신경병증 진행 차단을 위한 12주 집중 케어"),
        "dementia": ("Brain Vitality", "인지 기능 유지를 위한 10주 두뇌 케어"),
        "cerebro": ("Stroke Prevention", "뇌혈관 질환 예방을 위한 12주 집중 관리"),
    }
    # v2.3.0 (감사): ML 예측이 하나도 없으면(전 모델 실패) 특정 프로그램을 근거 없이
    #   추천하지 않고 일반 프로그램으로 안내한다.
    if not available_radar:
        prog_name, prog_desc = (
            "DB-care Basic",
            "합병증 예측 모델을 불러오지 못해 종합 관리 프로그램을 안내합니다",
        )
    else:
        prog_name, prog_desc = program_map.get(
            max_risk, ("DB-care Basic", "당뇨 합병증 종합 관리")
        )

    return {
        # v2.2.2 (F2): 시나리오 정책의 임상 안전망을 반영한 radar_display 응답
        "radar": radar_display,
        "neglect": neglect,
        "intensive": intensive,
        "graduation": graduation,
        "fold_change_by_disease": fold_change_by_disease,
        # v2.1.9 — 질환별 모델 threshold (0~100). 프론트가 일관 등급화에 사용.
        "risk_thresholds": get_disease_thresholds(age=age),
        "recommended_program": {
            "name": prog_name,
            "description": prog_desc,
        },
        # v2.1 — baseline-aware 시뮬레이션 메타 정보 (프론트가 라벨 분기 / 안내 표시에 사용)
        "meta": {
            "mean_score": round(mean_score, 1),
            "baseline_severity": round(baseline_sev, 2),
            "slider_changed": slider_changed,
            "drift_worse": round(drift_worse, 2),
            "drift_better": round(drift_better, 2),
            "slider_drift_threshold": 0.5,
            "excluded_floor_rules": list(SCENARIO_EXCLUDED_FLOOR_RULES),
            "floor_policy_note": SCENARIO_FLOOR_POLICY_NOTE,
        },
        "clinical_note": "DCCT·UKPDS 기반: HbA1c 1% 감소 시 미세혈관 합병증 25~37% 감소가 보고되었습니다.",
    }


@router.post("/scenario/simulate")
def scenario_simulate(body: ScenarioRequest, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == body.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    pdict = _patient_to_dict(patient)
    # v2.2.2 (H3): 표시/예측 나이 통일 — 현재 만나이(dob 기준), fallback 저장 age.
    age = _current_age_calc(pdict) or patient.age or 60
    data = build_scenario_payload(
        patient, pdict, age,
        sim_hba1c=body.hba1c, sim_cpep=body.c_peptide,
        base_hba1c=patient.hba1c or 7.5, base_cpep=patient.c_peptide or 2.0,
    )
    return {"data": data, "success": True}
