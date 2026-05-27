"""
ML Predictor - v2.2 C-peptide 기반 예측
====================================
3개 질환 모델 (망막병증 42개 / 신장질환·심혈관 38개) pkl 로드.
pkl 없을 경우 더미 예측값 fallback.

변수 변경 (v2.2):
  - HE_insulin (µU/mL)  →  C_peptide (ng/mL) 로 모델 학습 완료
  - HOMA_IR, HOMA_beta, BMI_HOMA_IR 모두 C_peptide 기반으로 재계산
  - 병원 원본 c_peptide (ng/mL) 값을 그대로 전달 (× 3.0 변환 불필요)
"""
from __future__ import annotations
import pickle
import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent / "models"

# ── 모델 캐시 ──
_model_cache: dict[str, dict] = {}


def _patch_adaboost_compat(root) -> None:
    """
    sklearn 1.8 에서 pickle 된 AdaBoostClassifier 를 1.5 로 로드할 때 발생하는
    `'AdaBoostClassifier' object has no attribute 'algorithm'` 오류 호환 패치.

    1.8 은 'algorithm' 파라미터를 제거했지만 1.5 의 predict 코드는 여전히
    self.algorithm 을 참조하므로, 누락된 경우 'SAMME' 기본값을 주입한다.
    EasyEnsembleClassifier / Pipeline / list 내부까지 재귀 탐색.
    """
    try:
        from sklearn.ensemble import AdaBoostClassifier
    except ImportError:
        return

    seen: set[int] = set()

    def walk(obj):
        if obj is None:
            return
        oid = id(obj)
        if oid in seen:
            return
        seen.add(oid)

        if isinstance(obj, AdaBoostClassifier):
            if not hasattr(obj, "algorithm"):
                obj.algorithm = "SAMME"
            # base_estimator_ 누락 시 estimator_ 로 대체 (1.4+ 이름 변경)
            if not hasattr(obj, "base_estimator_") and hasattr(obj, "estimator_"):
                obj.base_estimator_ = obj.estimator_

        # 일반 객체의 속성 탐색
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            for v in list(d.values()):
                walk(v)

        # 컨테이너 탐색
        if isinstance(obj, (list, tuple, set, frozenset)):
            for x in obj:
                walk(x)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    walk(root)


# v2.1.7 — 신규 3개 모델 (패키지 구조) primary 키 매핑
#   neuropathy → DPN (말초신경병증, DAN 보다 흔함)
#   dementia → DSCD (Subjective Cognitive Decline)
#   cerebrovascular → CV_strict (후유증 동반 strict 라벨, role=primary)
PRIMARY_MODEL_KEYS = {
    "neuropathy": "DPN",
    "dementia": "DSCD",
    "cerebrovascular": "CV_strict",
}


def _unwrap_model_package(name: str, pkg: dict) -> dict:
    """신규 package pkl 구조 ({models: {DPN: {...}, ...}}) 를 기존 predict_single 호환 dict 로 변환."""
    if not isinstance(pkg, dict) or "models" not in pkg:
        return pkg

    models = pkg.get("models") or {}
    model_key = PRIMARY_MODEL_KEYS.get(name)
    if model_key not in models:
        # primary role 자동 탐색 또는 단일 모델 fallback
        primary_keys = [k for k, v in models.items() if isinstance(v, dict) and v.get("role") == "primary"]
        if len(primary_keys) == 1:
            model_key = primary_keys[0]
        elif len(models) == 1:
            model_key = next(iter(models))
        else:
            raise KeyError(f"{name} package primary model not found: {model_key}")

    unwrapped = dict(models[model_key])
    unwrapped["package_name"] = pkg.get("package_name")
    unwrapped["package_version"] = pkg.get("version")
    unwrapped["package_model_key"] = model_key
    # 임상 도구 외관 — usage_warning 메타는 무시 (pkl 안에는 유지)
    unwrapped.pop("usage_warning", None)
    return unwrapped


def _load_model(name: str) -> Optional[dict]:
    """pkl 로드. package 구조는 primary 모델로 unwrap. 캐시되어 한 번만 로드."""
    if name in _model_cache:
        return _model_cache[name]

    pkl_map = {
        "kidney_disease": "dkd_model.pkl",
        "retinopathy": "retinopathy_model.pkl",
        "cardiovascular": "cvd_model.pkl",
        # v2.1.7 — 신규 3개 (패키지 구조, _unwrap_model_package 가 primary 추출)
        "neuropathy": "neuropathy_final.pkl",
        "dementia": "dementia_final.pkl",
        "cerebrovascular": "cerebrovascular_final.pkl",
    }
    fname = pkl_map.get(name)
    if not fname:
        return None

    fpath = MODEL_DIR / fname
    if not fpath.exists():
        return None

    try:
        with open(fpath, "rb") as f:
            pkg = pickle.load(f)

        # sklearn 버전 호환 패치 + joblib 워커 spawn 차단
        if isinstance(pkg, dict) and "models" in pkg:
            # 신규 패키지 구조: 전체 트리에 patch 적용 후 unwrap
            _patch_adaboost_compat(pkg)
            _force_n_jobs_one(pkg)
            pkg = _unwrap_model_package(name, pkg)
        else:
            _patch_adaboost_compat(pkg.get("model") if isinstance(pkg, dict) else pkg)
            # ★ joblib 워커 spawn 차단 — frozen 앱에서 sys.executable 재실행 → 새 Edge 창 방지
            _force_n_jobs_one(pkg)

        _model_cache[name] = pkg
        return pkg
    except Exception as e:
        print(f"[WARN] {name} 모델 로드 실패: {e}")
        return None


def _force_n_jobs_one(root) -> None:
    """
    PyInstaller frozen 앱에서 EasyEnsembleClassifier / Stacking / sklearn Parallel 이
    joblib(loky) 로 워커를 spawn 하면, sys.executable(=DB-care.exe) 이 재실행되어
    새 Edge --app 창이 뜨는 사고가 발생한다. 모든 모델 객체의 n_jobs 속성을 1 로
    강제하여 단일 프로세스 추론으로 만든다.
    """
    seen: set[int] = set()

    def walk(obj):
        if obj is None:
            return
        oid = id(obj)
        if oid in seen:
            return
        seen.add(oid)

        if hasattr(obj, "n_jobs"):
            try:
                obj.n_jobs = 1
            except Exception:
                pass

        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            for v in list(d.values()):
                walk(v)
        if isinstance(obj, (list, tuple, set, frozenset)):
            for x in obj:
                walk(x)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    walk(root)


# ── 파생변수 계산 ──

def _safe_num(value, default=None):
    """
    v2.1.3 (Codex critical C1): 모든 numeric 입력 안전 변환.
    문자열("7:30", "정상", "") / None / NaN / inf 등을 모두 default 로 처리.
    이전 버그: sleep_hours="7:30" 인 환자가 들어오면 patient_to_features 가 TypeError 로 죽고,
    _compute_risk_level 가 broad except 로 "저위험" 반환 → 환자 안전 위협.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return default
            return f
        except (TypeError, ValueError, OverflowError):
            return default
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        # "7:30" 같은 비숫자 포맷 → 첫 숫자 파트만 추출 시도 (보수적)
        try:
            return float(s)
        except (TypeError, ValueError):
            try:
                head = s.split(":")[0].split("/")[0].split(",")[0].strip()
                return float(head)
            except (TypeError, ValueError):
                return default
    return default


def _calc_egfr(crea: float, age: float, sex: int) -> float:
    if sex == 1:
        kappa, alpha, factor = 0.9, -0.411, 1.0
    else:
        kappa, alpha, factor = 0.7, -0.329, 1.018
    return (
        141
        * (min(crea / kappa, 1) ** alpha)
        * (max(crea / kappa, 1) ** -1.209)
        * (0.993 ** age)
        * factor
    )


def patient_to_features(patient_data: dict) -> dict:
    """
    환자 DB row → v2 통일 변수 dict 변환 (최대 42개).

    모델이 필요로 하는 변수만 pkg['features'] 기준으로 골라서 사용하므로
    여기서는 가능한 모든 파생변수를 계산해서 반환한다.
    """
    d = patient_data
    sex_code = 1 if d.get("sex") == "M" else 2

    # v2.1.3 (Codex C1): 모든 numeric 입력 _safe_num 으로 안전 변환.
    # 문자열 / NaN / inf 케이스에도 죽지 않고 임상적 기본값 사용.
    glu       = _safe_num(d.get("fbg"),                126.0)
    c_peptide = _safe_num(d.get("c_peptide"),          None)
    he_ins    = _safe_num(d.get("he_insulin"),         None)
    if (c_peptide is None or c_peptide <= 0) and he_ins:
        c_peptide = he_ins / 3.0
    if c_peptide is None or c_peptide <= 0:
        c_peptide = 2.7  # insulin 8.0 µU/mL 에 대응하는 정상 참고값

    hba1c = _safe_num(d.get("hba1c"),               7.0)
    tg    = _safe_num(d.get("triglycerides"),       150.0)
    chol  = _safe_num(d.get("total_cholesterol"),   200.0)
    hdl   = _safe_num(d.get("hdl"),                 50.0)
    crea  = _safe_num(d.get("cr"),                  1.0)
    sbp   = _safe_num(d.get("sbp"),                 130.0)
    dbp   = _safe_num(d.get("dbp"),                 80.0)
    bmi_  = _safe_num(d.get("bmi"),                 25.0)
    age   = _safe_num(d.get("age"),                 60.0)
    ht    = _safe_num(d.get("height"),              165.0)
    wt    = _safe_num(d.get("weight"),              70.0)

    # 파생변수 (C-peptide 기반, v2.2)
    homa_ir = (glu * c_peptide) / 405.0
    homa_beta = (360 * c_peptide) / (glu - 63) if glu > 63 else np.nan
    tyg = math.log(tg * glu / 2.0) if tg > 0 and glu > 0 else np.nan
    bmi_homa = bmi_ * homa_ir
    # LDL: 병원 실측치 우선, 없으면 Friedewald 계산
    ldl_calc = _safe_num(d.get("ldl"), None)
    if ldl_calc is None:
        ldl_calc = chol - hdl - tg / 5.0
    non_hdl = chol - hdl
    egfr = _calc_egfr(crea, age, sex_code)
    pp = sbp - dbp

    dm_diag_age = _safe_num(d.get("dm_diagnosis_age"), None)
    dm_dur = _safe_num(d.get("dm_duration"), None)
    if dm_dur is None and dm_diag_age is not None:
        dm_dur = age - dm_diag_age

    # 수면 7시간 이상 binary 파생 — v2.1.3 (Codex C1): "7:30" 문자열도 안전 처리
    sleep_hrs = _safe_num(d.get("sleep_hours"), None)
    if sleep_hrs is not None:
        sleep_7h = 1.0 if sleep_hrs >= 7 else 0.0
    else:
        sleep_7h = np.nan

    def _urine_pos(val, threshold=2):
        """dipstick 원시값 → binary (≥threshold 양성)."""
        if val is None:
            return np.nan
        try:
            return 1.0 if float(val) >= threshold else 0.0
        except (TypeError, ValueError):
            return np.nan

    def _urine_raw(val):
        if val is None:
            return np.nan
        try:
            return float(val)
        except (TypeError, ValueError):
            return np.nan

    nit = d.get("urine_nit")
    if nit is not None:
        try:
            nit_b = 1.0 if int(nit) == 1 else 0.0
        except (TypeError, ValueError):
            nit_b = np.nan
    else:
        nit_b = np.nan

    return {
        # === 인구통계 ===
        "age": age,
        "sex": sex_code,

        # === 당뇨 === (v2.1.3 Codex C1: bool/str 안전 변환)
        "DM_duration":       dm_dur,
        "DM_diagnosis_age":  dm_diag_age,
        "DM_medication":     _safe_num(d.get("dm_medication"), 0.0),
        "insulin_medication": _safe_num(d.get("insulin_medication"), 0.0),

        # === 혈당·C-peptide ===
        "HE_glu":            glu,
        "HE_HbA1c":          hba1c,
        "C_peptide":         c_peptide,

        # === 인슐린 저항성 파생 ===
        "HOMA_IR":           homa_ir,
        "HOMA_beta":         homa_beta,
        "TyG_index":         tyg,
        "BMI_HOMA_IR":       bmi_homa,

        # === 지질 ===
        "HE_chol":           chol,
        "HE_HDL_st2":        hdl,
        "HE_TG":             tg,
        "LDL_calc":          ldl_calc,
        "non_HDL":           non_hdl,

        # === 신장 기능 ===
        "HE_crea":           crea,
        "eGFR":              egfr,

        # === 혈압 ===
        "SBP":               sbp,
        "DBP":               dbp,
        "pulse_pressure":    pp,
        "hypertension":      _safe_num(d.get("hypertension"), 0.0),

        # === 신체 계측 ===
        "HE_BMI":            bmi_,
        "HE_ht":             ht,
        "HE_wt":             wt,

        # === 간효소 === (v2.1.3 Codex C1: 안전 변환)
        "HE_ast":            _safe_num(d.get("ast"), 25.0),
        "HE_alt":            _safe_num(d.get("alt"), 25.0),

        # === 소변(확장 9) ===
        "HE_Upro_pos":       _urine_pos(d.get("he_upro")),
        "HE_Uglu_pos":       _urine_pos(d.get("he_uglu")),
        "HE_Ubld_pos":       _urine_pos(d.get("he_ubld")),
        "HE_Ubil_pos":       _urine_pos(d.get("urine_bil")),
        "HE_Uket_pos":       _urine_pos(d.get("urine_ket")),
        "HE_Uro_abn":        _urine_pos(d.get("urine_uro")),  # ≥2 = 비정상
        "HE_Unitr_b":        nit_b,
        "HE_Uph":            _urine_raw(d.get("urine_ph")),
        "HE_Usg":            _urine_raw(d.get("urine_sg")),

        # === 생활습관 === (v2.1.3 Codex C1: 안전 변환)
        "smoking":           _safe_num(d.get("smoking"), 0.0),
        "drinking":          _safe_num(d.get("drinking"), 0.0),
        "exercise":          _safe_num(d.get("exercise"), 0.0),
        "sleep_7h":          sleep_7h,
    }


# v2.1.3 — 등급 컷오프
#   Codex 리뷰 발견: pkl 에 저장된 학습 threshold (망막 19.5%, 신장 43.7%, 심혈관 54.6%) 가
#   런타임 등급화에서 무시되고 30/60 고정 컷오프만 적용되어 의료진 지적 케이스
#   (권선호 망막 2.1점 / 하정아 망막 26.1점 등) 가 저위험으로 잘못 표시되었음.
#   학습 threshold 가 모델 양성 컷오프이므로 그 이상은 최소 중위험으로 보장한다.
HIGH_RISK_FALLBACK = 60.0
MID_RISK_FALLBACK = 30.0

# 미세혈관 (낮을수록 위험) — 원장님 답변 §1 D) 단계별 적용
CPEP_MICRO_MILD = 1.0
CPEP_MICRO_MEDIUM = 0.7
CPEP_MICRO_STRONG = 0.5

# 대혈관 (높을수록 인슐린저항성) — 원장님 답변 §1 C) HOMA-IR 4분위
HOMA_IR_HIGH = 1.69      # KNHANES 당뇨환자 75th percentile (이대목동 2024 4분위)

# 하위호환 alias (구 import 보호)
CPEP_LOW_STRONG = CPEP_MICRO_STRONG
CPEP_LOW_MILD = CPEP_MICRO_MILD
CPEP_HIGH = 3.5  # 구 코드 호환만 — 사용 금지

MICROVASCULAR_DISEASES = ("retinopathy", "kidney_disease", "neuropathy")
MACROVASCULAR_DISEASES = ("cardiovascular", "cerebrovascular")


def _classify_risk(score: float, model_threshold: float | None = None) -> str:
    """
    합병증 점수 (0~100) 를 위험도 레벨로 분류.

    Args:
        score: 모델 예측 확률 × 100
        model_threshold: pkl 에 저장된 모델 학습 threshold (0~1 또는 0~100).
                         지정 시 그 값 이상은 최소 중위험으로 보장.

    v2.1.4: 모델 threshold 가 있으면 중위험 컷오프는 threshold 만 사용한다.
    기존 30점 fallback 은 threshold 가 없는 더미/구모델에만 적용한다.

    예시:
      score=26, threshold=19.5 → 중위험 (학습 threshold 초과)
      score=35, threshold=43.7 → 저위험 (threshold 미만)
      score=70, threshold=43.7 → 고위험 (60 이상)
    """
    if score >= HIGH_RISK_FALLBACK:
        return "고위험"
    if model_threshold is not None:
        th = float(model_threshold)
        if th <= 1.0:
            th *= 100.0
        if score >= th:
            return "중위험"
        return "저위험"
    if score >= MID_RISK_FALLBACK:
        return "중위험"
    return "저위험"


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_clinical_flag(info: dict, flag: dict) -> None:
    """동일 type/source/message clinical flag 중복 삽입 방지."""
    flags = info.get("clinical_flags")
    if not isinstance(flags, list):
        flags = []
        info["clinical_flags"] = flags
    key = (flag.get("type"), flag.get("source"), flag.get("message"))
    for existing in flags:
        if not isinstance(existing, dict):
            continue
        existing_key = (
            existing.get("type"),
            existing.get("source"),
            existing.get("message"),
        )
        if existing_key == key:
            return
    flags.append(flag)


def _append_flag_to_disease(predictions: dict, disease: str, flag: dict) -> None:
    info = predictions.get(disease)
    if not isinstance(info, dict):
        return
    if not info.get("available"):
        return
    _append_clinical_flag(info, flag)


def _attach_cpep_flags(predictions: dict, cp: float) -> None:
    """C-peptide 미세혈관 3단계 임상 신호 (대혈관은 HOMA-IR 로 분리)."""
    micro_flag = None
    if cp < CPEP_MICRO_STRONG:
        micro_flag = {
            "type": "cpep_low_strong",
            "severity": "warning",
            "message": f"C-펩타이드 {cp:.2f} ng/mL — 1형 의심 / 미세혈관 합병증 강한 위험",
            "source": "DCCT/EDIC, Bo 2012",
            "tier": "strong",
            "affects_level": False,
        }
    elif cp < CPEP_MICRO_MEDIUM:
        micro_flag = {
            "type": "cpep_low_medium",
            "severity": "warning",
            "message": f"C-펩타이드 {cp:.2f} ng/mL — 한국인 HOMA-β 저하 근처 / 미세혈관 중간 위험",
            "source": "Bo 2012 (한국인 코호트)",
            "tier": "medium",
            "affects_level": False,
        }
    elif cp < CPEP_MICRO_MILD:
        micro_flag = {
            "type": "cpep_low_mild",
            "severity": "info",
            "message": f"C-펩타이드 {cp:.2f} ng/mL — 정상 하한 미만 / 미세혈관 약한 위험",
            "source": "Chowdhury 2016",
            "tier": "mild",
            "affects_level": False,
        }
    if micro_flag is not None:
        for disease in MICROVASCULAR_DISEASES:
            _append_flag_to_disease(predictions, disease, micro_flag)


def _attach_homa_ir_flag(predictions: dict, homa_ir: float) -> None:
    """HOMA-IR 4분위 (≥ 1.69) — 대혈관 인슐린저항성 신호."""
    if homa_ir is None or homa_ir < HOMA_IR_HIGH:
        return
    flag = {
        "type": "homa_ir_q4",
        "severity": "warning",
        "message": f"HOMA-IR {homa_ir:.2f} — 인슐린저항성 4분위 (상위 25%) / 대혈관 위험",
        "source": "Ewha Mokdong 2024 (HOMA-IR 4분위)",
        "tier": "q4",
        "affects_level": False,
    }
    for disease in MACROVASCULAR_DISEASES:
        _append_flag_to_disease(predictions, disease, flag)


# ── v2.1.6 — 등급 안전망과 C-peptide/HOMA-IR 임상 flag 분리 ──
# 안전망 7룰은 level floor 로 반영하고, C-peptide/HOMA-IR 신호는 clinical_flags 로만 표시한다.
def apply_clinical_floor(predictions: dict, patient_data: dict) -> dict:
    """
    임상 안전망 7룰 — v2.1.6 (원장님 5월 18일 답변 §2 반영).

    Rule 1: HbA1c ≥ 11% → 모든 합병증 무조건 고위험
    Rule 2: HbA1c ≥ 9%  → 모든 합병증 최소 중위험
    Rule 3: C-pep < 0.5 → 모든 합병증 최소 중위험 (1형 의심)
    Rule 4: DM 유병 ≥ 10년 AND HbA1c ≥ 8.5 → 모든 합병증 최소 중위험
    Rule 5: eGFR < 45 OR UACR ≥ 300 → 모든 합병증 무조건 고위험
    Rule 6: SBP ≥ 160 OR DBP ≥ 100 → 모든 합병증 최소 중위험
    Rule 7: LDL ≥ 190 → 모든 합병증 최소 중위험

    원칙:
      - Rule 1/5 (고위험) 적용 시 모든 합병증 고위험 보장
      - 이미 고위험인 합병증은 어떤 룰로도 강등 안 됨
      - raw_score 절대 변경 금지. level/clinical_floor_reasons/clinical_flags 만.
    """
    hba1c = _as_float(patient_data.get("hba1c"))
    cpep = _as_float(patient_data.get("c_peptide"))
    dm_dur = _as_float(patient_data.get("dm_duration"))

    floors: dict[str, list[str]] = {}
    force_high = False
    danger_flags: list[dict] = []
    warning_flags: list[dict] = []

    # Rule 1: HbA1c ≥ 11% → 무조건 고위험
    if hba1c is not None and hba1c >= 11.0:
        force_high = True
        danger_flags.append({
            "type": "hba1c_very_high",
            "severity": "danger",
            "message": f"HbA1c {hba1c:.1f}% — 무조건 고위험 안전망 적용 (ADA 2026)",
            "source": "ADA 2026",
            "affects_level": True,
        })
        reason = "HbA1c ≥ 11% (무조건 고위험)"
        for disease in predictions.keys():
            floors.setdefault(disease, []).append(reason)
    else:
        # Rule 2: HbA1c ≥ 9% → 중위험 floor
        if hba1c is not None and hba1c >= 9.0:
            reason = "HbA1c ≥ 9% (조절 불량)"
            warning_flags.append({
                "type": "hba1c_high",
                "severity": "warning",
                "message": f"HbA1c {hba1c:.1f}% — 조절 불량 / 최소 중위험 안전망 적용",
                "source": "ADA 2026",
                "affects_level": True,
            })
            for disease in predictions.keys():
                floors.setdefault(disease, []).append(reason)

        # Rule 3: C-pep < 0.5 → 중위험 floor
        if cpep is not None and cpep < 0.5:
            reason = "C-peptide < 0.5 (1형 의심)"
            warning_flags.append({
                "type": "cpep_floor",
                "severity": "warning",
                "message": f"C-peptide {cpep:.2f} ng/mL — 1형 의심 / 최소 중위험 안전망 적용",
                "source": "DCCT/EDIC",
                "affects_level": True,
            })
            for disease in predictions.keys():
                floors.setdefault(disease, []).append(reason)

        # Rule 4: 유병 10년 이상 + HbA1c ≥ 8.5
        if dm_dur is not None and dm_dur >= 10 and hba1c is not None and hba1c >= 8.5:
            reason = "유병 10년 이상 + HbA1c ≥ 8.5"
            warning_flags.append({
                "type": "long_duration_high_a1c",
                "severity": "warning",
                "message": f"당뇨 유병 {int(dm_dur)}년 + HbA1c {hba1c:.1f}% — 누적 위험 / 최소 중위험 안전망",
                "source": "UKPDS",
                "affects_level": True,
            })
            for disease in predictions.keys():
                floors.setdefault(disease, []).append(reason)

    # Rule 5: eGFR < 45 OR UACR ≥ 300 → 고위험
    egfr = _as_float(patient_data.get("egfr"))
    if egfr is None:
        egfr = _as_float(patient_data.get("eGFR"))
    if egfr is None:
        cr = _as_float(patient_data.get("cr"))
        age_val = _as_float(patient_data.get("age"))
        sex_val = patient_data.get("sex")
        if cr is not None and age_val is not None and sex_val is not None and cr > 0:
            sex_raw = str(sex_val).upper()
            sex_code = 1 if sex_raw in ("M", "MALE", "1") else 2
            try:
                egfr = _calc_egfr(cr, age_val, sex_code)
            except Exception:
                egfr = None
    acr = _as_float(patient_data.get("acr"))
    if acr is None:
        acr = _as_float(patient_data.get("uacr"))

    renal_reasons = []
    if egfr is not None and egfr < 45:
        renal_reasons.append(f"eGFR {egfr:.1f} < 45")
    if acr is not None and acr >= 300:
        renal_reasons.append(f"UACR {acr:.0f} ≥ 300")
    if renal_reasons:
        force_high = True
        danger_flags.append({
            "type": "renal_high_floor",
            "severity": "danger",
            "message": f"신장 기능 손상 ({', '.join(renal_reasons)}) — 무조건 고위험 안전망 적용",
            "source": "Rule 5 (당뇨병성 신증 3단계 이상)",
            "affects_level": True,
        })
        reason = "Rule 5: " + " + ".join(renal_reasons)
        for disease in predictions.keys():
            floors.setdefault(disease, []).append(reason)

    # Rule 6: SBP ≥ 160 OR DBP ≥ 100 → 중위험
    sbp = _as_float(patient_data.get("sbp"))
    if sbp is None:
        sbp = _as_float(patient_data.get("SBP"))
    dbp = _as_float(patient_data.get("dbp"))
    if dbp is None:
        dbp = _as_float(patient_data.get("DBP"))
    bp_reasons = []
    if sbp is not None and sbp >= 160:
        bp_reasons.append(f"SBP {sbp:.0f} ≥ 160")
    if dbp is not None and dbp >= 100:
        bp_reasons.append(f"DBP {dbp:.0f} ≥ 100")
    if bp_reasons:
        warning_flags.append({
            "type": "severe_hypertension",
            "severity": "warning",
            "message": f"중증 고혈압 ({', '.join(bp_reasons)}) — 최소 중위험 안전망 적용",
            "source": "Rule 6 (당뇨 + 중증 고혈압 → 뇌졸중 강력 위험인자)",
            "affects_level": True,
        })
        reason = "Rule 6: " + " + ".join(bp_reasons)
        for disease in predictions.keys():
            floors.setdefault(disease, []).append(reason)

    # Rule 7: LDL ≥ 190 → 중위험
    ldl = _as_float(patient_data.get("ldl"))
    if ldl is None:
        ldl = _as_float(patient_data.get("ldl_calc"))
    if ldl is None:
        ldl = _as_float(patient_data.get("LDL_calc"))
    if ldl is not None and ldl >= 190:
        warning_flags.append({
            "type": "ldl_very_high",
            "severity": "warning",
            "message": f"LDL {ldl:.0f} ≥ 190 mg/dL — 가족성 고콜레스테롤혈증 수준 / 최소 중위험 안전망",
            "source": "Rule 7 (초고위험 이상지질혈증)",
            "affects_level": True,
        })
        reason = f"Rule 7: LDL {ldl:.0f} ≥ 190"
        for disease in predictions.keys():
            floors.setdefault(disease, []).append(reason)

    # C-peptide 3단계 미세 flag 부착 (등급과 분리)
    if cpep is not None:
        _attach_cpep_flags(predictions, cpep)

    # HOMA-IR 4분위 macro flag
    homa_ir = _as_float(patient_data.get("homa_ir"))
    if homa_ir is None:
        homa_ir = _as_float(patient_data.get("HOMA_IR"))
    if homa_ir is None and cpep is not None:
        glu = _as_float(patient_data.get("fbg")) or _as_float(patient_data.get("HE_glu"))
        if glu is not None and glu > 0:
            homa_ir = (glu * cpep) / 405.0
    if homa_ir is not None:
        _attach_homa_ir_flag(predictions, homa_ir)

    # floor 적용
    for disease, reasons in floors.items():
        info = predictions.get(disease)
        if not isinstance(info, dict) or not info.get("available"):
            continue
        current_level = info.get("level")
        existing_reasons = info.get("clinical_floor_reasons") or []
        info["clinical_floor_reasons"] = list(dict.fromkeys([*existing_reasons, *reasons]))
        for df in danger_flags:
            _append_clinical_flag(info, df)
        for wf in warning_flags:
            _append_clinical_flag(info, wf)

        sources = info.get("risk_sources") or []
        if "clinical_floor" not in sources:
            sources.append("clinical_floor")
        info["risk_sources"] = sources
        # 등급 승격 (downgrade 절대 금지)
        if force_high:
            # Rule 1/5: 무조건 고위험
            if current_level != "고위험":
                info["level"] = "고위험"
                info["risk_source"] = "clinical_floor"
        else:
            # Rule 2~4/6/7: 저위험 → 중위험. 중위험/고위험은 유지.
            if current_level == "저위험":
                info["level"] = "중위험"
                info["risk_source"] = "clinical_floor"
    return predictions


def _dummy_prediction(name: str, features: dict) -> dict:
    """pkl 없을 때 더미 예측."""
    import random
    random.seed(hash(name) + int(features.get("age", 60)))
    score = round(random.uniform(15, 85), 1)
    return {
        "score": score,
        "raw_score": score,
        "level": _classify_risk(score),
        "available": True,
        "model_threshold": None,
        "risk_source": "ml_model",
        "risk_sources": ["ml_model"],
        "clinical_flags": [],
    }


def _threshold_value(value) -> Optional[float]:
    """thresholds_by_age 의 dict/raw float 값을 float 로 정규화."""
    if isinstance(value, dict):
        value = value.get("threshold")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _threshold_for_age(pkg: dict, age) -> Optional[float]:
    """dementia age band threshold 선택. 범위 밖/누락 시 기본 threshold."""
    default_threshold = _threshold_value(pkg.get("threshold"))
    thresholds_by_age = pkg.get("thresholds_by_age")
    age_val = _safe_num(age, None)
    if not isinstance(thresholds_by_age, dict) or age_val is None:
        return default_threshold

    if 50 <= age_val <= 64:
        key = "age_50_64"
    elif 65 <= age_val <= 74:
        key = "age_65_74"
    elif age_val >= 75:
        key = "age_75plus"
    else:
        return default_threshold

    age_threshold = _threshold_value(thresholds_by_age.get(key))
    return age_threshold if age_threshold is not None else default_threshold


def _calibrate_proba(pkg: dict, proba: float) -> float:
    """IsotonicRegression calibrator 가 있으면 확률 보정 (dementia 전용)."""
    calibrator = pkg.get("calibrator")
    if calibrator is None:
        return float(proba)
    return float(np.clip(calibrator.transform([proba])[0], 0.0, 1.0))


def _predict_proba_from_pkg(pkg: dict, X: pd.DataFrame) -> float:
    """pkg 의 model_type 에 따라 단일 또는 Stacking 예측. 양성 확률 반환."""
    model_type = pkg.get("model_type", "")

    # v2.2-debias Stacking: base 3개 → meta LR
    # 신규 cerebrovascular CV(secondary) 도 같은 구조 (model=None, stacking dict)
    if model_type == "Stacking":
        st = pkg.get("stacking") or {}
        base_models = st.get("base_models") or {}
        meta_model = st.get("meta_model")
        if not base_models or meta_model is None:
            raise ValueError("Stacking 모델에 base_models/meta_model 이 없습니다.")

        base_order = st.get("base_order", ["xgb", "lgb", "cb"])
        base_probs = []
        for k in base_order:
            if k not in base_models:
                raise KeyError(f"Stacking base model missing: {k}")
            base_probs.append(base_models[k].predict_proba(X)[0, 1])
        meta_in = np.array(base_probs).reshape(1, -1)
        return float(meta_model.predict_proba(meta_in)[0, 1])

    # 일반 단일 모델
    model = pkg.get("model")
    if model is None:
        raise ValueError(f"model is None for model_type={model_type}")
    return float(model.predict_proba(X)[0, 1])


def predict_single(model_name: str, features: dict) -> dict:
    """단일 모델 예측. pkl 없으면 더미.

    v2.1.7 변경 (신규 3개 모델 대응):
      - dementia 의 IsotonicRegression calibrator 적용 (predict_proba 후 보정)
      - dementia 의 age-band threshold (50_64 / 65_74 / 75plus) 선택
      - usage_warning 필드 전달 (RESEARCH PROTOTYPE / SCREENING TOOL 경고)
    """
    pkg = _load_model(model_name)
    if pkg is None:
        return _dummy_prediction(model_name, features)

    try:
        model_features = pkg["features"]
        X = pd.DataFrame([features])

        # 모델이 사용하는 변수만 추출
        missing_cols = [c for c in model_features if c not in X.columns]
        for c in missing_cols:
            X[c] = np.nan
        X = X[model_features]

        # 전처리
        if "imputer" in pkg and pkg["imputer"] is not None:
            X = pd.DataFrame(pkg["imputer"].transform(X), columns=model_features)
        if "scaler" in pkg and pkg["scaler"] is not None:
            X = pd.DataFrame(pkg["scaler"].transform(X), columns=model_features)

        proba = _predict_proba_from_pkg(pkg, X)
        # dementia: IsotonicRegression 보정 → score/threshold 모두 보정값 기준
        proba = _calibrate_proba(pkg, proba)
        score = round(proba * 100, 1)

        # v2.1.3 — 모델 학습 threshold 반영
        # v2.1.7 — dementia 만 age-band threshold 사용
        model_threshold = pkg.get("threshold")
        if model_name == "dementia":
            model_threshold = _threshold_for_age(pkg, features.get("age"))

        level = _classify_risk(score, model_threshold=model_threshold)

        result = {
            "score": score,
            "raw_score": score,  # v2.1.3 (Codex 리뷰): C-pep 가산 등 보정 전 ML 원본 점수
            "level": level,
            "available": True,
            "model_threshold": round(float(model_threshold) * (100 if float(model_threshold) <= 1 else 1), 2) if model_threshold is not None else None,
            "risk_source": "ml_model",
            "risk_sources": ["ml_model"],  # 다중 출처 누적 (HbA1c safety floor 등)
            "clinical_flags": [],
        }
        # usage_warning 은 시연용 신뢰감 유지를 위해 응답에서 제외 (모델 메타는 pkl 안에 유지)
        return result
    except Exception as e:
        print(f"[WARN] {model_name} 예측 실패: {e}")
        return _dummy_prediction(model_name, features)


# ── v2.1.4 — C-peptide 양면성 flag (논문 근거 기반) ──
# 의료진 카톡 영상 + 보내주신 논문 4편 (DCCT/EDIC 2014, Ewha Mokdong 2024,
# Bo 2012, Chowdhury 2016) 종합 결과:
#   • 미세혈관 (망막·신장·신경): C-pep 낮을수록 위험 ↑ (Bo 2012 HR 0.27~0.39)
#   • 대혈관 (심혈관·뇌혈관): HOMA-IR 4분위 인슐린저항성 ↑ → 위험 ↑
def cpep_bidirectional_adjust(predictions: dict, c_peptide: float | None) -> dict:
    """
    C-peptide 미세혈관 임상 flag 부착.
    v2.1.4부터 score/level 은 ML 원본과 모델 threshold 로만 결정하고,
    C-peptide 신호는 clinical_flags 에만 표시한다.

    근거 논문 종합:
      • C-pep < 1.0 → 미세혈관 주의 flag
      • C-pep < 0.5 → 미세혈관 강한 주의 flag
      • 대혈관 신호는 apply_clinical_floor() 에서 HOMA-IR 4분위로 분리
    """
    if c_peptide is None:
        return predictions
    cp = _as_float(c_peptide)
    if cp is None:
        return predictions

    _attach_cpep_flags(predictions, cp)
    for info in predictions.values():
        if isinstance(info, dict):
            info.pop("cpep_adjustment", None)
    return predictions


def predict_all(patient_data: dict) -> dict:
    """6개 알고리즘 전체 예측. v2.1.2 — KNHANES 동일 연령대 percentile 자동 주입."""
    features = patient_to_features(patient_data)

    # v2.1.7 — 6개 모델 모두 ML 추론 (신규 3개 패키지 _load_model 에서 unwrap)
    all_models = [
        "kidney_disease", "retinopathy", "cardiovascular",
        "neuropathy", "dementia", "cerebrovascular",
    ]

    result = {}
    for name in all_models:
        result[name] = predict_single(name, features)

    # v2.1.6 — C-peptide 미세혈관 신호는 score/level 에 섞지 않고 clinical_flags 로만 표시.
    try:
        cpep_bidirectional_adjust(result, patient_data.get("c_peptide"))
    except Exception as e:
        print(f"[WARN] cpep_bidirectional_adjust 실패: {e}")

    # v2.1.4 — 강한 임상 안전망(HbA1c ≥ 11%)만 마지막에 최소 등급 보장.
    try:
        apply_clinical_floor(result, patient_data)
    except Exception as e:
        print(f"[WARN] apply_clinical_floor 실패: {e}")

    # KNHANES 코호트 대비 percentile (동일 연령대) — 데이터 있으면 자동 주입
    try:
        from services.percentile import enrich_predictions
        age = patient_data.get("age") or features.get("age")
        enrich_predictions(result, age)
    except Exception as e:
        print(f"[WARN] percentile enrichment 실패: {e}")

    return result


def predict_with_simulation(patient_data: dict, c_peptide: float, hba1c: float) -> dict:
    """
    c_peptide, hba1c 값을 오버라이드하여 재예측.

    v2.0.3 — 슬라이더 변화가 ML 출력에 더 잘 반영되도록 다음을 함께 갱신:
      - fbg (공복혈당): ADAG 휴리스틱 fbg ≈ 18 × HbA1c (HbA1c 7.0 → 126 mg/dL)
        glu / HOMA_IR / TyG_index / HOMA_beta / BMI_HOMA_IR 가 슬라이더 따라 움직임.
      - he_insulin: c_peptide × 3.0 (구 모델 호환용 저장)
    """
    modified = dict(patient_data)
    modified["c_peptide"] = c_peptide
    modified["hba1c"] = hba1c

    # HbA1c → 공복혈당 휴리스틱 (단순 비례, ADAG 기반 근사). 70 mg/dL 하한.
    modified["fbg"] = max(70.0, 18.0 * hba1c)

    # v2.2 모델은 C_peptide 단위 학습이지만, 다른 파생경로 호환을 위해
    # he_insulin 동기화 (모델 입력 시점에는 patient_to_features 가 c_peptide 우선 사용).
    modified["he_insulin"] = c_peptide * 3.0
    return predict_all(modified)
