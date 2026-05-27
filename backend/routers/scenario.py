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
from ml.predictor import predict_with_simulation

router = APIRouter(prefix="/api/v1", tags=["scenario"])


# ── 유틸 ──

def _patient_to_dict(p: Patient) -> dict:
    return {c.name: getattr(p, c.name) for c in p.__table__.columns}


def _level(score):
    if score is None:
        return "중위험"
    if score >= 60:
        return "고위험"
    if score >= 30:
        return "중위험"
    return "저위험"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _stable_offset(seed_key: str, lo: float, hi: float) -> float:
    """환자+질환 조합별 고정 오프셋. 슬라이더가 움직여도 변하지 않음."""
    h = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16)
    frac = (h % 10000) / 10000.0  # 0.0 ~ 1.0
    return lo + frac * (hi - lo)


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

@router.post("/scenario/simulate")
def scenario_simulate(body: ScenarioRequest, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == body.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    pdict = _patient_to_dict(patient)
    age = patient.age or 60
    hba1c_current = patient.hba1c or 7.5
    cpep_current = patient.c_peptide or 2.0

    # ── ML 예측 (3개 로드된 모델만 실제 proba) ──
    # predict_with_simulation 이 이미 body.c_peptide / body.hba1c 를 features 에 반영해서
    # 예측하므로 ML 모델은 슬라이더 효과를 자체적으로 흡수한다.
    current_pred = predict_with_simulation(pdict, body.c_peptide, body.hba1c)

    # ── 슬라이더 가시성 보정 ──
    # v2.1.3 (Codex 리뷰 반영): 실 ML 점수에는 sensitivity 가산 적용 X.
    # ML 모델이 이미 슬라이더 값을 입력으로 받아 점수를 산출했기 때문에 추가 가산은 이중 반영.
    # sensitivity 는 ML 미구현 모델 (신경병증·치매·뇌혈관) 의 휴리스틱 참고값에만 적용.
    sensitivity = _slider_sensitivity_boost(
        base_hba1c=hba1c_current,
        base_cpep=cpep_current,
        cur_hba1c=body.hba1c,
        cur_cpep=body.c_peptide,
    )

    # ── Radar 데이터 (6개 합병증 점수) ──
    name_map = {
        "kidney_disease": "kidney",
        "retinopathy": "retina",
        "cardiovascular": "cardio",
        "neuropathy": "neuro",
        "dementia": "dementia",
        "cerebrovascular": "cerebro",
    }

    radar = {}
    for full_name, short_name in name_map.items():
        pred = current_pred.get(full_name, {})
        score = pred.get("score")
        if score is None:
            # 미구현 모델 → 슬라이더 반응 가능한 휴리스틱 참고값 + sensitivity 적용
            score = _pending_reference_score(
                patient.id, short_name, patient,
                hba1c=body.hba1c, c_peptide=body.c_peptide,
            )
            # 미구현 모델은 ML 예측이 없으므로 sensitivity 로 슬라이더 변화 시각화
            score = round(_clamp(score + sensitivity, 1, 99), 1)
        else:
            # 실 ML 점수 그대로 사용 (predict_with_simulation 이 이미 슬라이더 반영)
            score = round(_clamp(score, 1, 99), 1)
        radar[short_name] = score

    # ── v2.1 baseline-aware 시뮬레이션 ──
    # 환자의 현 합병증 평균 점수 + 슬라이더 변화량(악화/개선 방향) 두 축으로
    # 방치/집중관리 시나리오의 강도를 결정. 저위험 환자에게 과장된 경고가 나가지 않게.
    mean_score, baseline_sev = _baseline_severity(radar)
    drift_worse, drift_better = _slider_drift(
        hba1c_current, cpep_current, body.hba1c, body.c_peptide
    )
    # 슬라이더 변화 임계값 — HbA1c 0.5% 또는 C-peptide 0.5 ng/mL 정도 움직였을 때만 "변경됨" 판정.
    # 사용자가 무심코 0.1~0.3 정도 만지는 건 baseline 으로 간주해서 톤 유지.
    slider_changed = (drift_worse + drift_better) > 0.5
    # 합병증 평균 점수가 저위험 컷오프(< 30) 미만이고 슬라이더가 크게 안 움직였으면
    # "방치" 대신 "현재 수치 유지" 라벨 사용. _classify_risk 와 동일 컷오프로 정합성 유지.
    neglect_label_mode = "maintain" if (mean_score < 30 and not slider_changed) else "neglect"

    # ── 방치/현재유지 시 시나리오 ──
    neglect_complications = {}
    for short in radar:
        if short in PENDING_MODELS:
            neglect_complications[short] = {"level": "분석 진행 중", "score": None}
        else:
            worsened = _worsen(radar[short], baseline_sev, drift_worse)
            neglect_complications[short] = {"level": _level(worsened), "score": worsened}

    # 건강수명 감소 — baseline severity + 악화 방향 drift 가 클수록 큼.
    # 저위험 + 슬라이더 그대로 → 1년 미만 (사실상 변화 없음).
    life_hit = _clamp(baseline_sev * 12.0 + drift_worse * 3.0, 0.5, 18.0)

    # 의료비 절대치 — 환자 baseline 위험에 비례. 슬라이더 악화도 반영.
    cost_base = int(80 + baseline_sev * 350 + drift_worse * 100)
    # 의료비 증가율 — 저위험 환자는 +5% 정도, 고위험 + 큰 악화 → +130%
    cost_increase_pct = int(_clamp(baseline_sev * (15 + drift_worse * 50), 5, 130))

    # 인슐린 시작 확률 — 저위험 환자는 거의 0, 고위험 + 악화 → 90%
    insulin_prob = int(_clamp(baseline_sev * (15 + drift_worse * 60), 2, 90))

    # 당뇨약 개수 추정
    drug_before = 1 if (body.hba1c < 7.5 and baseline_sev < 0.5) else 2
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
        "annual_cost_man": max(120, cost_base + int(baseline_sev * 200)),
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
    intensive_complications = {}
    for short in radar:
        if short in PENDING_MODELS:
            intensive_complications[short] = {"level": "분석 진행 중", "score": None}
        else:
            improved = _improve(radar[short], baseline_sev, drift_better)
            intensive_complications[short] = {"level": _level(improved), "score": improved}

    hba1c_after = max(5.5, body.hba1c - 1.0)

    # v2.1.2 — C-peptide 변화는 정상범위(1.0~3.5)를 향해 수렴해야 의학적으로 옳음.
    #   • > 3.5: 인슐린 저항성 보상으로 과분비 중 → 관리 시 정상범위로 ↓
    #   • < 1.0: 췌장 기능 저하 → 관리해도 최대 1.0~1.3 까지만 회복
    #   • 1.0~3.5 (정상): 인슐린 저항성 개선으로 약간 ↓ (단, 1.0 미만으로 떨어지지 않게)
    NORMAL_CPEP_LO, NORMAL_CPEP_HI = 1.0, 3.5
    if body.c_peptide > NORMAL_CPEP_HI:
        # 과분비 상태 → 정상 상한 근처까지 ↓
        cpep_after = max(NORMAL_CPEP_HI - 0.3, body.c_peptide - 0.8)
    elif body.c_peptide < NORMAL_CPEP_LO:
        # 췌장기능 저하 → 약간 회복 (1.0~1.3 사이)
        cpep_after = min(NORMAL_CPEP_LO + 0.3, body.c_peptide + 0.3)
    else:
        # 정상범위 → 인슐린 저항성 개선으로 약간 ↓ (단 1.0 보장)
        cpep_after = max(NORMAL_CPEP_LO, body.c_peptide - 0.3)
    cpep_after = round(cpep_after, 2)

    # 건강수명 회복 — 저위험 환자는 작은 회복(이미 건강), 고위험 환자는 큰 회복.
    life_gain = _clamp(baseline_sev * 5.0 + drift_better * 3.0, 1.0, 8.0)
    cost_after = int(_clamp(cost_base * 0.4, 60, 400))
    cost_decrease_pct = int(_clamp(20 + baseline_sev * 25 + drift_better * 10, 15, 55))

    # 집중관리 건강수명 — age + 3 이상, 방치보다 +2 이상.
    intensive_life_raw = int(82 - (age / 10) + life_gain)
    intensive_life = max(60, age + 3, neglect_life + 2, intensive_life_raw)

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
        "cost_decrease_pct": cost_decrease_pct,
        "hba1c_before": round(body.hba1c, 1),
        "hba1c_after": round(hba1c_after, 1),
        "cpeptide_before": round(body.c_peptide, 1),
        "cpeptide_after": round(cpep_after, 1),
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

    # ── 졸업시 시나리오 (v2.1.5 — 표준 졸업값 고정, 슬라이더 영향 없음) ──
    GRADUATION_VALUES = {
        "hba1c": 5.5,
        "c_peptide": 2.0,
        "fbg": 90.0,
        "sbp": 120.0,
        "dbp": 80.0,
        "bmi": 22.0,
    }

    grad_patient = dict(pdict)
    grad_patient.update({
        "hba1c": GRADUATION_VALUES["hba1c"],
        "c_peptide": GRADUATION_VALUES["c_peptide"],
        "fbg": GRADUATION_VALUES["fbg"],
        "sbp": GRADUATION_VALUES["sbp"],
        "dbp": GRADUATION_VALUES["dbp"],
        "bmi": GRADUATION_VALUES["bmi"],
    })
    grad_pred = predict_with_simulation(
        grad_patient,
        GRADUATION_VALUES["c_peptide"],
        GRADUATION_VALUES["hba1c"],
    )

    grad_complications = {}
    for full_name, short_name in name_map.items():
        pred = grad_pred.get(full_name, {})
        score = pred.get("score")
        if score is None:
            score = _pending_reference_score(
                patient.id, short_name, patient,
                hba1c=GRADUATION_VALUES["hba1c"],
                c_peptide=GRADUATION_VALUES["c_peptide"],
            )
            score = round(_clamp(score * 0.4, 5, 25), 1)
        else:
            score = round(_clamp(score, 1, 99), 1)
        grad_complications[short_name] = {
            "level": _level(score),
            "score": score,
        }

    # 졸업 수명: age 만 의존하는 표준 졸업값 (슬라이더 영향 차단)
    grad_life = int(82 - age / 10 + 4)
    grad_cost = int(_clamp(60 + age * 0.5, 50, 150))

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

    # ── 추천 프로그램 (실제 ML 모델 3개 중 가장 높은 위험도 기반) ──
    available_radar = {k: v for k, v in radar.items() if k in AVAILABLE_MODELS}
    max_risk = max(available_radar, key=available_radar.get) if available_radar else "kidney"
    program_map = {
        "kidney": ("Kidney Shield", "신장 기능 보존을 위한 12주 집중 케어"),
        "retina": ("Vision Guard", "망막 건강 보호를 위한 8주 맞춤 프로그램"),
        "cardio": ("Heart Care Plus", "심혈관 위험 관리를 위한 12주 통합 케어"),
        "neuro": ("Neuropathy Guard", "신경병증 진행 차단을 위한 12주 집중 케어"),
        "dementia": ("Brain Vitality", "인지 기능 유지를 위한 10주 두뇌 케어"),
        "cerebro": ("Stroke Prevention", "뇌혈관 질환 예방을 위한 12주 집중 관리"),
    }
    prog_name, prog_desc = program_map.get(
        max_risk, ("DB-care Basic", "당뇨 합병증 종합 관리")
    )

    return {
        "data": {
            "radar": radar,
            "neglect": neglect,
            "intensive": intensive,
            "graduation": graduation,
            "fold_change_by_disease": fold_change_by_disease,
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
            },
            "clinical_note": "DCCT·UKPDS 기반: HbA1c 1% 감소 시 미세혈관 합병증 25~37% 감소가 보고되었습니다.",
        },
        "success": True,
    }
