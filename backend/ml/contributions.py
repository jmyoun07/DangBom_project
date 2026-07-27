"""환자별 변수 기여도 (SHAP) — '이 환자의 위험을 무엇이 올렸나'.

기존 UI 의 '1순위 요인'은 질환별로 고정된 지표(치매=나이, 신장=eGFR …)를
모든 환자에게 똑같이 보여줬다. 이 모듈은 그 환자의 예측에 실제로 기여한
변수를 SHAP 으로 산출해 환자마다 다른 근거를 제시한다.

설계상 중요한 두 가지 제약 (없으면 오히려 오정보가 된다):

1) 실측 변수만 후보 (MEASURED_FEATURES)
   병원은 운동·수면·흡연·음주·소변검사를 수집하지 않는다(실데이터 625명 중 0건).
   모델은 결측을 imputer 로 채우는데, 그 '채워진 값'이 SHAP 상위를 독식한다.
   실제로 제한 없이 돌리면 망막병증 1순위가 전 환자 '운동'으로 나왔다.
   → 병원이 실제로 측정하는 변수만 후보로 둔다.

2) 질환별 임상 화이트리스트 (CLINICAL_FEATURES)
   통계적 기여가 있어도 임상 인과가 약한 변수(예: 망막병증의 ALT/AST)를
   '1순위 요인'으로 제시하면 의료진이 납득할 수 없다.
   → 질환별로 의학적으로 설명 가능한 변수만 남긴다.

지원 모델: 단일 트리 모델(XGBoost 등). Stacking·EasyEnsemble 등 앙상블은
현재 미지원이며 None 을 반환한다(호출부는 기존 고정 표시로 폴백).
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# 병원이 실제로 측정하는 모델 변수 (수집률 0인 생활습관·소변 dipstick 제외)
MEASURED_FEATURES = frozenset({
    "age", "sex",
    "HE_HbA1c", "HE_glu", "C_peptide",
    "HE_crea", "eGFR",
    "SBP", "DBP", "pulse_pressure", "hypertension",
    "HE_chol", "HE_TG", "HE_HDL_st2", "LDL_calc", "non_HDL",
    "HE_BMI", "HE_ht", "HE_wt",
    "HE_ast", "HE_alt",
    "HOMA_IR", "HOMA_beta", "TyG_index", "BMI_HOMA_IR",
    "DM_duration", "DM_diagnosis_age",
})

# 질환별로 '1순위 요인'으로 제시해도 임상적으로 설명 가능한 변수
CLINICAL_FEATURES = {
    "retinopathy": {
        "HE_HbA1c", "HE_glu", "C_peptide", "DM_duration", "DM_diagnosis_age",
        "SBP", "DBP", "pulse_pressure", "hypertension", "age",
        "HE_TG", "LDL_calc", "non_HDL", "HE_chol", "HE_HDL_st2",
        "eGFR", "HE_crea", "HE_BMI", "HOMA_IR", "TyG_index",
    },
    "kidney_disease": {
        "eGFR", "HE_crea", "HE_HbA1c", "HE_glu", "SBP", "DBP", "pulse_pressure",
        "hypertension", "age", "DM_duration", "HE_BMI", "C_peptide",
        "HE_TG", "LDL_calc", "non_HDL", "HOMA_IR", "TyG_index",
    },
    "cardiovascular": {
        "SBP", "DBP", "pulse_pressure", "hypertension", "LDL_calc", "non_HDL",
        "HE_chol", "HE_HDL_st2", "HE_TG", "HE_HbA1c", "HE_glu", "age",
        "HE_BMI", "DM_duration", "eGFR", "HOMA_IR", "TyG_index", "sex",
    },
    "neuropathy": {
        "HE_HbA1c", "HE_glu", "DM_duration", "DM_diagnosis_age", "C_peptide",
        "age", "HE_TG", "HE_HDL_st2", "HE_BMI", "SBP", "eGFR", "HOMA_IR", "TyG_index",
    },
    "cerebrovascular": {
        "SBP", "DBP", "pulse_pressure", "hypertension", "HE_BMI", "HE_HbA1c",
        "HE_glu", "LDL_calc", "non_HDL", "HE_chol", "HE_HDL_st2", "HE_TG",
        "age", "DM_duration", "eGFR", "sex",
    },
    "dementia": {
        "age", "HE_HbA1c", "HE_glu", "SBP", "DBP", "hypertension", "HE_BMI",
        "DM_duration", "eGFR", "HE_chol", "HE_HDL_st2", "sex",
    },
}

# 화면 표시용 한글명 + 단위
FEATURE_LABELS = {
    "HE_HbA1c": ("당화혈색소", "%"),
    "HE_glu": ("공복혈당", " mg/dL"),
    "C_peptide": ("C-peptide", " ng/mL"),
    "HE_crea": ("크레아티닌", " mg/dL"),
    "eGFR": ("eGFR", " mL/min"),
    "SBP": ("수축기혈압", " mmHg"),
    "DBP": ("이완기혈압", " mmHg"),
    "pulse_pressure": ("맥압", " mmHg"),
    "hypertension": ("고혈압 동반", ""),
    "HE_chol": ("총콜레스테롤", " mg/dL"),
    "HE_TG": ("중성지방", " mg/dL"),
    "HE_HDL_st2": ("HDL", " mg/dL"),
    "LDL_calc": ("LDL", " mg/dL"),
    "non_HDL": ("non-HDL", " mg/dL"),
    "HE_BMI": ("BMI", ""),
    "HE_ht": ("키", " cm"),
    "HE_wt": ("몸무게", " kg"),
    "HE_ast": ("AST", " U/L"),
    "HE_alt": ("ALT", " U/L"),
    "HOMA_IR": ("인슐린저항성", ""),
    "HOMA_beta": ("췌장 베타세포 기능", ""),
    "TyG_index": ("TyG 지수", ""),
    "BMI_HOMA_IR": ("BMI×인슐린저항성", ""),
    "DM_duration": ("당뇨 유병기간", "년"),
    "DM_diagnosis_age": ("당뇨 진단 나이", "세"),
    "age": ("나이", "세"),
    "sex": ("성별", ""),
}

_EXPLAINER_CACHE: dict[int, object] = {}
_UNSUPPORTED: set[int] = set()


def _get_explainer(model):
    """모델별 SHAP TreeExplainer (캐시). 미지원 모델은 None."""
    key = id(model)
    if key in _UNSUPPORTED:
        return None
    cached = _EXPLAINER_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import shap
        expl = shap.TreeExplainer(model)
        _EXPLAINER_CACHE[key] = expl
        return expl
    except Exception as e:
        logger.info("[SHAP] 미지원 모델(%s): %s", type(model).__name__, e)
        _UNSUPPORTED.add(key)
        return None


# 값 대신 상태 문구로 보여줄 범주형 변수 ('성별 2.0' 같은 무의미한 표시 방지)
_CATEGORICAL = {
    "sex": {1: "남", 2: "여"},
    "hypertension": {0: "없음", 1: "있음"},
}

# 화면에 근거로 내보내지 않을 변수 (환자가 바꿀 수 없거나 설명력이 없음)
_HIDDEN = frozenset({"sex", "HE_ht"})


def _raw_value(feature: str, raw_features: dict):
    """스케일링 전 원본 값 (화면 표시용). 실측이 없으면 None.

    None 이면 그 변수는 후보에서 제외한다 — 결측을 imputer 가 채운 값이라
    '유병기간 None년' 처럼 근거가 될 수 없는 항목이 화면에 뜨는 것을 막는다.
    """
    v = raw_features.get(feature)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN (결측 → imputer 가 채운 값)
        return None
    cat = _CATEGORICAL.get(feature)
    if cat is not None:
        return cat.get(int(round(f)))
    return round(f, 1) if abs(f) >= 10 else round(f, 2)


def compute_contributions(disease: str, pkg: dict, X_scaled, raw_features: dict,
                          top_n: int = 3) -> list[dict] | None:
    """그 환자의 예측에 기여한 변수 상위 N개.

    Args:
        disease: 모델 키 (retinopathy / kidney_disease / …)
        pkg: 모델 패키지 dict (model·features 포함)
        X_scaled: predict 에 실제로 들어간 2D 배열 (1, n_features)
        raw_features: 스케일 전 원본 feature dict (표시용 값)
    Returns:
        [{feature, label, unit, value, shap, direction}] — shap 내림차순.
        미지원 모델·계산 실패 시 None (호출부는 기존 고정 표시로 폴백).
    """
    model = (pkg or {}).get("model")
    features = (pkg or {}).get("features")
    if model is None or not features:
        return None

    expl = _get_explainer(model)
    if expl is None:
        return None

    try:
        sv = expl.shap_values(X_scaled)
        arr = np.asarray(sv)
        if arr.ndim == 3:        # (n, features, classes) — 양성 클래스
            arr = arr[0, :, -1]
        elif arr.ndim == 2:
            arr = arr[0]
        if arr.shape[0] != len(features):
            return None
    except Exception as e:
        logger.info("[SHAP] %s 기여도 계산 실패: %s", disease, e)
        return None

    allowed = CLINICAL_FEATURES.get(disease, set()) & MEASURED_FEATURES
    if not allowed:
        allowed = MEASURED_FEATURES

    scored = []
    for i, name in enumerate(features):
        if name not in allowed or name in _HIDDEN:
            continue
        val = float(arr[i])
        if val != val:
            continue
        shown = _raw_value(name, raw_features)
        if shown is None:
            continue          # 실측이 없는(imputer 가 채운) 변수는 근거로 쓰지 않는다
        label, unit = FEATURE_LABELS.get(name, (name, ""))
        scored.append({
            "feature": name,
            "label": label,
            "unit": "" if isinstance(shown, str) else unit,
            "value": shown,
            "shap": round(val, 4),
            # up = 이 환자의 위험을 올린 방향, down = 낮춘 방향
            "direction": "up" if val > 0 else "down",
        })
    if not scored:
        return None

    # 위험을 올린 변수를 우선 제시하고, 없으면(전부 보호적) 영향 큰 순으로.
    ups = sorted([s for s in scored if s["shap"] > 0], key=lambda s: -s["shap"])
    picked = ups[:top_n] if ups else sorted(scored, key=lambda s: s["shap"])[:top_n]

    # 1위 대비 기여가 미미한(10% 미만) 항목은 노이즈라 제외 — '근거'로 제시할 수준이 아니다.
    if picked:
        cutoff = abs(picked[0]["shap"]) * 0.1
        picked = [p for p in picked if abs(p["shap"]) >= cutoff]
    return picked or None
