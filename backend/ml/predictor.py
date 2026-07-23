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
import logging
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from services.derived import current_age as _current_age_calc
from services.derived import current_dm_duration as _current_dm_dur_calc
from services.derived import normalize_sex

logger = logging.getLogger("dbcare.predictor")

# v2.2.2 (H4): 신규 3개는 저AUC(0.61~0.73) 선별용 — 임상 확정 모델과 구분 표시.
SCREENING_MODELS = {"neuropathy", "dementia", "cerebrovascular"}

# v2.1.8 — 모델 pkl 의 sklearn 학습 버전이 런타임과 달라 발생하는
# InconsistentVersionWarning 억제. 실측 검증 결과 KNNImputer/StandardScaler/
# IsotonicRegression 의 transform 결과는 1.5.2↔1.8.0 사이 0.000 차이로 동일하여
# 예측 정확성에는 영향이 없음. 로그/콘솔 오염만 막는다.
try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except Exception:
    pass

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
    """pkl 로드. package 구조는 primary 모델로 unwrap. 캐시되어 한 번만 로드.

    v2.1.9 (감사 B): 실패도 캐시(None sentinel)해 등급 조회마다 재시도하지 않는다
    (scenario 가 질환별 threshold 를 18회 조회하므로 실패 모델 반복 시도 방지).
    """
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
        logger.error("[MODEL MISSING] %s 파일 없음: %s", name, fpath)
        _model_cache[name] = None   # 실패 캐시 (재시도 방지)
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
        logger.error("[MODEL LOAD FAIL] %s: %s", name, e)
        _model_cache[name] = None   # 실패 캐시 (재시도 방지)
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


def _isnan(x) -> bool:
    """float NaN 판정 (비-float 은 False)."""
    return isinstance(x, float) and math.isnan(x)


def _calc_egfr(crea: float, age: float, sex: int) -> float:
    # v2.1.9 (감사 H3): Cr<=0 / age<=0 방어. 이전엔 가드가 없어 Cr=0 이면
    # min(0,1)**(-0.411) → inf/ZeroDivision 으로 비정상 eGFR 가 모델에 들어갔다.
    # derived.py _ckd_epi_egfr 와 동일한 가드로 통일.
    if crea is None or age is None or crea <= 0 or age <= 0:
        return np.nan
    if sex == 1:
        kappa, alpha, factor = 0.9, -0.411, 1.0
    elif sex == 2:
        kappa, alpha, factor = 0.7, -0.329, 1.018
    else:
        # v2.2.6 (감사 H1): 성별 불명(NaN)이면 여성 묵시 계산 금지 → NaN(imputer 처리).
        return np.nan
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
    # v2.2.2 (H3): age/dm_duration 정규화는 predict_all 진입부(_normalize_age_duration)에서
    #   1회 수행하므로 여기서는 정규화된 d 를 그대로 읽는다 (features·floor·percentile 일관).
    d = patient_data
    # v2.2.6 (감사 H1): 성별 단일 정규화 + 결측/불명은 NaN(여성 묵시 처리 금지 → imputer).
    _nsex = normalize_sex(d.get("sex"))
    sex_code = 1 if _nsex == "M" else (2 if _nsex == "F" else np.nan)

    # v2.1.3 (Codex C1): 모든 numeric 입력 _safe_num 으로 안전 변환.
    # 문자열 / NaN / inf 케이스에도 죽지 않고 임상적 기본값 사용.
    # v2.2.6 (감사 H2): 결측 핵심 측정값을 임상 하드디폴트로 메우지 않고 None 으로 두었다가
    #   출력 직전 NaN 으로 변환해 학습된 KNNImputer(pkg["imputer"])가 코호트 분포로 처리하게 한다
    #   (train/serve 결측처리 일치). 파생 계산은 None 가드로 NaN 전파.
    glu       = _safe_num(d.get("fbg"),                None)
    c_peptide = _safe_num(d.get("c_peptide"),          None)
    he_ins    = _safe_num(d.get("he_insulin"),         None)
    if (c_peptide is None or c_peptide <= 0) and he_ins:
        c_peptide = he_ins / 3.0       # 구데이터 호환: he_insulin/3 역추정
    if c_peptide is not None and c_peptide <= 0:
        c_peptide = None               # 비양수 → 결측 취급 (하드 2.7 제거)

    hba1c = _safe_num(d.get("hba1c"),               None)
    tg    = _safe_num(d.get("triglycerides"),       None)
    chol  = _safe_num(d.get("total_cholesterol"),   None)
    hdl   = _safe_num(d.get("hdl"),                 None)
    crea  = _safe_num(d.get("cr"),                  None)
    sbp   = _safe_num(d.get("sbp"),                 None)
    dbp   = _safe_num(d.get("dbp"),                 None)
    bmi_  = _safe_num(d.get("bmi"),                 None)
    age   = _safe_num(d.get("age"),                 None)
    ht    = _safe_num(d.get("height"),              None)
    wt    = _safe_num(d.get("weight"),              None)

    # 파생변수 (C-peptide 기반, v2.2) — 입력 결측이면 NaN 전파(→ imputer 처리).
    homa_ir = (glu * c_peptide) / 405.0 if (glu is not None and glu > 0 and c_peptide is not None and c_peptide > 0) else np.nan
    homa_beta = (360 * c_peptide) / (glu - 63) if (c_peptide is not None and glu is not None and glu > 63) else np.nan
    tyg = math.log(tg * glu / 2.0) if (tg is not None and glu is not None and tg > 0 and glu > 0) else np.nan
    bmi_homa = bmi_ * homa_ir if (bmi_ is not None and not _isnan(homa_ir)) else np.nan
    # LDL: 병원 실측치 우선, 없으면 Friedewald 계산
    # v2.1.9 (감사 H3): Friedewald 는 TG<400 에서만 신뢰 (derived.py 와 일치).
    # TG≥400/입력결측이면 NaN → imputer 가 처리.
    ldl_calc = _safe_num(d.get("ldl"), None)
    if ldl_calc is None:
        if chol is not None and hdl is not None and tg is not None and tg < 400:
            ldl_calc = chol - hdl - tg / 5.0
        else:
            ldl_calc = np.nan
    # v2.2.2 (M8): 모델 입력 경로도 음수 파생 차단 (HDL>총콜레스테롤 / SBP<DBP 비정상 입력).
    if ldl_calc is not None and not _isnan(ldl_calc) and ldl_calc < 0:
        ldl_calc = np.nan
    non_hdl = (chol - hdl) if (chol is not None and hdl is not None) else np.nan
    if not _isnan(non_hdl) and non_hdl < 0:
        non_hdl = np.nan
    egfr = _calc_egfr(crea, age, sex_code)  # crea/age None·성별 불명 시 np.nan
    pp = (sbp - dbp) if (sbp is not None and dbp is not None) else np.nan
    if not _isnan(pp) and pp < 0:
        pp = np.nan

    dm_diag_age = _safe_num(d.get("dm_diagnosis_age"), None)
    dm_dur = _safe_num(d.get("dm_duration"), None)
    if dm_dur is None and dm_diag_age is not None and age is not None:
        dm_dur = age - dm_diag_age
    # v2.2.2 (H3): 음수/비현실 이환기간 차단 (미래 dob·age 0 테스트환자 등 → imputer 처리)
    if dm_dur is not None and not (0 <= dm_dur <= 120):
        dm_dur = np.nan

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

    def _binary_yn(val):
        """생활습관 여부 → 이진(0=안함, ≥1=함). 결측/비수치/비유한은 NaN(→imputer).
        모델은 이진 학습이므로 병원 0~3 빈도 코드도 여기서 0/1 로 통일한다."""
        if val is None:
            return np.nan
        try:
            f = float(val)
        except (TypeError, ValueError):
            return np.nan
        if not math.isfinite(f):
            return np.nan
        return 1.0 if f >= 1 else 0.0

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

    # v2.2.6 (감사 H2): 결측(None) 핵심 측정값을 NaN 으로 → predict_single 의 KNNImputer 가 처리.
    #   (파생 계산은 위에서 None 가드로 이미 완료됨)
    age = age if age is not None else np.nan
    glu = glu if glu is not None else np.nan
    c_peptide = c_peptide if c_peptide is not None else np.nan
    hba1c = hba1c if hba1c is not None else np.nan
    tg = tg if tg is not None else np.nan
    chol = chol if chol is not None else np.nan
    hdl = hdl if hdl is not None else np.nan
    crea = crea if crea is not None else np.nan
    sbp = sbp if sbp is not None else np.nan
    dbp = dbp if dbp is not None else np.nan
    bmi_ = bmi_ if bmi_ is not None else np.nan
    ht = ht if ht is not None else np.nan
    wt = wt if wt is not None else np.nan
    dm_dur = dm_dur if dm_dur is not None else np.nan
    dm_diag_age = dm_diag_age if dm_diag_age is not None else np.nan

    return {
        # === 인구통계 ===
        "age": age,
        "sex": sex_code,

        # === 당뇨 === (v2.1.3 Codex C1: bool/str 안전 변환)
        # v2.3.0 (감사): 결측 약물여부를 0('없음')으로 단정하지 않고 NaN → imputer 위임.
        #   학습 데이터는 미상값을 NaN 으로 유지하므로 0 강제는 train/serve 불일치였음.
        "DM_duration":       dm_dur,
        "DM_diagnosis_age":  dm_diag_age,
        "DM_medication":     _safe_num(d.get("dm_medication"), np.nan),
        "insulin_medication": _safe_num(d.get("insulin_medication"), np.nan),

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
        # v2.3.0 (감사): 결측 고혈압여부 NaN → imputer 위임 (혈압값이 있으면 derived.py 가 이미 파생).
        "hypertension":      _safe_num(d.get("hypertension"), np.nan),

        # === 신체 계측 ===
        "HE_BMI":            bmi_,
        "HE_ht":             ht,
        "HE_wt":             wt,

        # === 간효소 === (v2.1.3 Codex C1: 안전 변환)
        "HE_ast":            _safe_num(d.get("ast"), np.nan),
        "HE_alt":            _safe_num(d.get("alt"), np.nan),

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
        # v2.3.0 (감사): 결측 생활습관을 0('안 함')으로 단정하지 않고 NaN → imputer 위임.
        # v2.3.3: 모델은 이진(0/1) 학습(build_unified: source==1)인데 병원 drinking/exercise 는
        #   0~3 빈도 코드 → '0=안함, ≥1=함'으로 이진화해 학습과 일치시킨다(원본은 DB에 그대로 저장).
        #   smoking 은 병원도 0/1 이라 결과 동일하나 일관성 위해 같은 규칙 적용.
        "smoking":           _binary_yn(d.get("smoking")),
        "drinking":          _binary_yn(d.get("drinking")),
        "exercise":          _binary_yn(d.get("exercise")),
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
# v2.2.9: 'C-peptide 결핍/저기능 의심 → 최소 중위험' floor 임계.
#   이론(0.5 nmol/L≈1.5 ng/mL)은 병원 C-peptide 참고범위 하한(1.0 ng/mL)과 충돌해
#   (1.0~1.5 구간이 '참고범위상 정상'이자 '결핍 의심'이 됨) 졸업기준(1.3)·집중관리 목표까지
#   floor 에 갇히는 문제가 있었다. 원장 결정: 병원 참고범위 하한과 동일한 1.0 으로 완화.
#   → C-peptide < 1.0 ng/mL(참고범위 하한 미만)만 인슐린 분비능 저하로 보고 중위험 floor.
CPEP_T1DM_SUSPECT = 1.0

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
      score=70, threshold=43.7 → 고위험 (60 이상 + threshold 이상)

    v2.1.9 (감사 — 등급 경계 통일): 고위험 = score>=60 AND score>=threshold.
    threshold 는 모델 "양성/주의" 컷오프이므로 중위험 기준으로 쓰고, 고위험은
    절대위험 60 을 유지하되 threshold 미만이면 고위험으로 올리지 않는다.
    이 함수가 backend/frontend/scenario 모든 등급화의 단일 진실 소스.
    """
    if score is None:
        return None
    if model_threshold is not None:
        th = float(model_threshold)
        if th <= 1.0:
            th *= 100.0
        if score >= HIGH_RISK_FALLBACK and score >= th:
            return "고위험"
        if score >= th:
            return "중위험"
        return "저위험"
    # threshold 없는 더미/구모델: 30/60 fallback
    if score >= HIGH_RISK_FALLBACK:
        return "고위험"
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
ALL_CLINICAL_FLOOR_RULES = frozenset(range(1, 8))


def _enabled_clinical_floor_rules(enabled_rules) -> frozenset[int]:
    """호출별 임상 안전망 정책을 불변 집합으로 정규화한다."""
    enabled = (
        ALL_CLINICAL_FLOOR_RULES
        if enabled_rules is None
        else frozenset(enabled_rules)
    )
    unknown = enabled - ALL_CLINICAL_FLOOR_RULES
    if unknown:
        raise ValueError(f"알 수 없는 임상 안전망 rule: {sorted(unknown)}")
    return enabled


def apply_clinical_floor(
    predictions: dict,
    patient_data: dict,
    enabled_rules=None,
) -> dict:
    """
    임상 안전망 7룰 — v2.1.6 (원장님 5월 18일 답변 §2 반영).

    Rule 1: HbA1c ≥ 11% → 모든 합병증 무조건 고위험
    Rule 2: HbA1c ≥ 9%  → 모든 합병증 최소 중위험
    Rule 3: C-pep < 1.0 ng/mL (참고범위 하한 미만) → 모든 합병증 최소 중위험 (인슐린 분비능 저하 의심, v2.2.9 원장 결정)
    Rule 4: DM 유병 ≥ 10년 AND HbA1c ≥ 8.5 → 모든 합병증 최소 중위험
    Rule 5: eGFR < 45 OR UACR ≥ 300 → 모든 합병증 무조건 고위험
    Rule 6: SBP ≥ 160 OR DBP ≥ 100 → 모든 합병증 최소 중위험
    Rule 7: LDL ≥ 190 → 모든 합병증 최소 중위험

    원칙:
      - enabled_rules=None 이면 기존 정책(1~7) 전체 적용
      - Rule 1/5 (고위험) 적용 시 모델 unavailable 포함 모든 합병증 고위험 보장
      - 이미 고위험인 합병증은 어떤 룰로도 강등 안 됨
      - raw_score 절대 변경 금지. level/clinical_floor_reasons/clinical_flags 만.
    """
    enabled = _enabled_clinical_floor_rules(enabled_rules)
    hba1c = _as_float(patient_data.get("hba1c"))
    cpep = _as_float(patient_data.get("c_peptide"))
    dm_dur = _as_float(patient_data.get("dm_duration"))

    floors: dict[str, list[str]] = {}
    force_high = False
    danger_flags: list[dict] = []
    warning_flags: list[dict] = []

    # Rule 1: HbA1c ≥ 11% → 무조건 고위험
    rule1_triggered = 1 in enabled and hba1c is not None and hba1c >= 11.0
    if rule1_triggered:
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
        if 2 in enabled and hba1c is not None and hba1c >= 9.0:
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

        # Rule 3: C-pep < 1.0 ng/mL (병원 참고범위 하한 미만) → 중위험 floor (v2.2.9, 원장 결정)
        if 3 in enabled and cpep is not None and cpep < CPEP_T1DM_SUSPECT:
            reason = "C-peptide < 1.0 ng/mL (참고범위 하한 미만 · 인슐린 분비능 저하 의심)"
            warning_flags.append({
                "type": "cpep_floor",
                "severity": "warning",
                "message": f"C-peptide {cpep:.2f} ng/mL (< 1.0 ng/mL 참고범위 하한) — 인슐린 분비능 저하 의심 / 최소 중위험 안전망 적용",
                "source": "DCCT/EDIC",
                "affects_level": True,
            })
            for disease in predictions.keys():
                floors.setdefault(disease, []).append(reason)

        # Rule 4: 유병 10년 이상 + HbA1c ≥ 8.5
        if (
            4 in enabled
            and dm_dur is not None
            and dm_dur >= 10
            and hba1c is not None
            and hba1c >= 8.5
        ):
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
    if 5 in enabled:
        egfr = _as_float(patient_data.get("egfr"))
        if egfr is None:
            egfr = _as_float(patient_data.get("eGFR"))
        if egfr is None:
            cr = _as_float(patient_data.get("cr"))
            age_val = _as_float(patient_data.get("age"))
            sex_val = patient_data.get("sex")
            if cr is not None and age_val is not None and sex_val is not None and cr > 0:
                _nsx = normalize_sex(sex_val)
                sex_code = 1 if _nsx == "M" else (2 if _nsx == "F" else None)
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
    if 6 in enabled:
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
    if 7 in enabled:
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
        if not isinstance(info, dict):
            continue
        # Rule 1/5 는 모델 예측 가능 여부와 무관한 강제 고위험 안전망이다.
        # 중위험 floor 는 모델 unavailable 응답의 예측불가 상태를 그대로 유지한다.
        if not info.get("available") and not force_high:
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


def clinical_floor_levels(patient_data: dict, diseases, enabled_rules=None) -> dict:
    """주어진 값으로 임상 안전망 7룰이 강제하는 '최소 등급'만 계산한다.

    점수/모델 예측 없이 floor 등급만 필요할 때 사용 (예: 시나리오 집중관리에서
    개선된 수치 hba1c_after/cpep_after 에 대한 안전망 등급 재평가). apply_clinical_floor
    를 단일 진실 소스로 재사용하므로 7룰이 중복 정의되지 않는다.

    Args:
        patient_data: hba1c/c_peptide/egfr/sbp/dbp/ldl/dm_duration 등 평가할 값.
        diseases: 등급을 받을 질환 키 목록 (predict_all 의 full name 권장).
        enabled_rules: 적용할 임상 안전망 번호. None 이면 기존 1~7 전체.

    Returns:
        {disease: '고위험'|'중위험'|None}.  None = 해당 질환 안전망 미발동.
    """
    stub = {d: {"available": True, "level": "저위험", "raw_score": 0.0} for d in diseases}
    try:
        apply_clinical_floor(stub, patient_data, enabled_rules=enabled_rules)
    except Exception as e:
        logger.error("[SAFETY] clinical_floor_levels 실패: %s", e)
        return {d: None for d in diseases}
    out = {}
    for d in diseases:
        lvl = stub[d].get("level")
        out[d] = lvl if lvl in ("중위험", "고위험") else None
    return out


def _floor_band_score(score, level, model_name, age=None):
    """진행바/게이지용 display 점수를 등급(level) 밴드 하한까지 올린다 (강등 없음).

    임상 안전망으로 level 만 승격되고 raw score 는 낮을 때(예: HbA1c≥11 로 고위험인데
    ML score 1.0) "고위험 배지 + 1/100 바" 모순을 막는다.

    v2.2.2 (이질감 개선): 안전망으로 6개가 모두 고위험으로 고정될 때 raw score 가 전부 60 미만이면
    바가 전부 60 으로 납작해져 똑같아 보였다. 이제 고위험 밴드 안에서 **raw 점수를 비례 반영**해
    ML 의 상대 위험 차이를 살린다 (모두 60 이상 = 고위험 zone 유지, 강등 없음).
      - 고위험: display = max(score, base + score×0.4)  (base = max(60, threshold)), 99 상한
      - 중위험: threshold ≤ display < 60
    raw_score(score)는 건드리지 않고 별도 display_score 로만 쓴다.
    """
    if score is None or level not in ("중위험", "고위험"):
        return round(score, 1) if score is not None else score
    th = get_disease_threshold(model_name, age=age)
    if level == "고위험":
        base = max(60.0, th or 60.0)
        return round(min(max(score, base + score * 0.4), 99.0), 1)
    lo = th or MID_RISK_FALLBACK
    return round(min(max(score, lo), 59.9), 1)


def _unavailable_prediction(name: str, reason: str = "model_unavailable") -> dict:
    """모델 로드/예측 실패 시 — 가짜 더미값 대신 '예측 불가' 를 명확히 반환.

    v2.1.9 (감사 C1): 환자 안전. 이전에는 random.uniform 더미 점수를
    available=True 로 반환해 모델이 깨져도 정상 예측처럼 보였다 (의료 오진 위험).
    이제 score/level=None + available=False 로 UI 가 "예측 불가" 를 표시하게 한다.
    배포본에서 이 경로 도달은 모델 번들(.pkl) 누락/의존성 문제이므로 ERROR 로 남긴다.
    """
    logger.error("[MODEL UNAVAILABLE] '%s' 예측 불가: %s", name, reason)
    return {
        "score": None,
        "raw_score": None,
        "level": None,
        "available": False,
        "model_threshold": None,
        "risk_source": "unavailable",
        "risk_sources": [],
        "error": reason,
        "clinical_flags": [],
    }


# v2.2.8 (병원 정책 — 완전한 기록만 예측, 추정 금지):
#   예측에 필요한 핵심 임상값이 하나라도 없으면 KNHANES 추정으로 채우지 않고 예측 자체를 거부한다.
#   ManualPatientForm.jsx 의 required 와 일치. (소변/생활습관/간효소 등 보조지표는 제외)
REQUIRED_CLINICAL_FIELDS = [
    ("age", "나이"), ("sex", "성별"),
    ("hba1c", "당화혈색소"), ("fbg", "공복혈당"), ("c_peptide", "C-peptide"),
    ("total_cholesterol", "총콜레스테롤"), ("triglycerides", "중성지방"), ("hdl", "HDL"),
    ("cr", "크레아티닌"),
    ("sbp", "수축기혈압"), ("dbp", "이완기혈압"),
    ("height", "키"), ("weight", "몸무게"),
]


def missing_required_fields(patient_data: dict) -> list:
    """필수 임상값 중 결측(없음/빈값/비수치)인 항목의 한글 라벨 목록. 비어 있으면 완전한 기록."""
    missing = []
    for key, label in REQUIRED_CLINICAL_FIELDS:
        v = patient_data.get(key)
        if key == "sex":
            if normalize_sex(v) is None:
                missing.append(label)
        elif _safe_num(v, None) is None:
            missing.append(label)
    return missing


def _insufficient_prediction(name: str, missing: list) -> dict:
    """필수 검사 누락 — 추정으로 채우지 않고 '데이터 부족'을 명확히 반환.

    _unavailable_prediction(모델 로드 실패)과 구분: risk_source='insufficient_data'.
    UI 는 이 값을 보고 '필수 검사 부족(누락: …)' 을 표시하고, 예측 점수는 내지 않는다.
    """
    return {
        "score": None,
        "raw_score": None,
        "level": None,
        "available": False,
        "model_threshold": None,
        "risk_source": "insufficient_data",
        "risk_sources": [],
        "error": "insufficient_data",
        "missing_required": missing,
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


# ── 등급 경계 단일 진실 소스 (감사 — 등급 불일치 통일) ──
# scenario.py / 프론트가 자체 30/60 고정값을 쓰지 않고 이 함수들을 통해
# 모델 학습 threshold 기준으로 일관되게 등급화한다.
DISEASE_MODEL_NAMES = (
    "kidney_disease", "retinopathy", "cardiovascular",
    "neuropathy", "dementia", "cerebrovascular",
)
# 프론트/시나리오의 짧은 키 → 모델명 매핑
DISEASE_ALIASES = {
    "kidney": "kidney_disease", "retina": "retinopathy",
    "cardio": "cardiovascular", "neuro": "neuropathy",
    "dementia": "dementia", "cerebro": "cerebrovascular",
}


def _threshold_percent(value) -> Optional[float]:
    """threshold 를 0~100 scale 로 정규화."""
    th = _threshold_value(value)
    if th is None:
        return None
    return round(th * 100.0 if th <= 1.0 else th, 2)


def get_disease_threshold(disease: str, age=None) -> Optional[float]:
    """질환의 모델 학습 threshold (0~100). dementia 는 age-band 반영."""
    name = DISEASE_ALIASES.get(disease, disease)
    pkg = _load_model(name)
    if pkg is None:
        return None
    raw = _threshold_for_age(pkg, age) if name == "dementia" else pkg.get("threshold")
    return _threshold_percent(raw)


def get_disease_thresholds(age=None) -> dict:
    """6개 질환의 threshold dict (짧은 키 기준). 프론트/시나리오 응답에 포함."""
    out = {}
    for short, full in DISEASE_ALIASES.items():
        out[short] = get_disease_threshold(full, age=age)
    return out


def classify_disease_risk(score, disease: str, age=None) -> Optional[str]:
    """질환별 모델 threshold 로 등급화 (단일 진실 소스)."""
    return _classify_risk(score, get_disease_threshold(disease, age=age))


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
        return _unavailable_prediction(model_name, "model_not_loaded")

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
            # v2.2.2 (H1): 진행바/게이지용 display 점수. floor 승격 시 predict_all 최종패스에서 갱신.
            "display_score": score,
            "level": level,
            "available": True,
            # v2.2.2 (H4): 신규 3개 저AUC 모델을 '선별(screening)' 로 표기 → UI 가 "참고용·임상확인 필요" 배지.
            "model_role": "screening" if model_name in SCREENING_MODELS else "clinical",
            "model_threshold": round(float(model_threshold) * (100 if float(model_threshold) <= 1 else 1), 2) if model_threshold is not None else None,
            "risk_source": "ml_model",
            "risk_sources": ["ml_model"],  # 다중 출처 누적 (HbA1c safety floor 등)
            "clinical_flags": [],
        }
        # usage_warning 은 시연용 신뢰감 유지를 위해 응답에서 제외 (모델 메타는 pkl 안에 유지)
        return result
    except Exception as e:
        logger.error("[PREDICT ERROR] %s 예측 실패: %s", model_name, e)
        return _unavailable_prediction(model_name, f"prediction_error: {type(e).__name__}")


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


def _normalize_age_duration(patient_data: dict) -> dict:
    """v2.2.2 (H3): 현재 만나이/이환기간을 주입한 새 dict 반환.

    features(patient_to_features) · 임상 안전망(apply_clinical_floor) · percentile 이
    모두 동일한 '현재 나이'를 쓰도록 predict_all 진입부에서 1회 정규화한다.
    (이전 버그: features 는 현재나이, floor 는 저장 dm_duration 을 읽어 Rule4 가 어긋남)
    """
    d = dict(patient_data)
    ca = _current_age_calc(d)
    if ca is not None:
        d["age"] = ca
        cd = _current_dm_dur_calc(d)
        if cd is not None:
            d["dm_duration"] = cd
    return d


def predict_all(patient_data: dict, enabled_rules=None) -> dict:
    """6개 알고리즘 전체 예측. enabled_rules=None 은 기존 1~7 안전망 전체."""
    # v2.2.2 (H3): 현재 age/dm_duration 정규화 → features/floor/percentile 전부 일관.
    patient_data = _normalize_age_duration(patient_data)

    # v2.1.7 — 6개 모델 모두 ML 추론 (신규 3개 패키지 _load_model 에서 unwrap)
    all_models = [
        "neuropathy", "retinopathy", "kidney_disease",
        "cardiovascular", "cerebrovascular", "dementia",
    ]

    # v2.2.8 (병원 정책): 필수 임상값이 하나라도 없으면 추정으로 채우지 않고 예측을 거부한다.
    #   완전한 검사 기록만 예측 — 6개 합병증 전부 '데이터 부족'으로 반환하고 imputer 경로를 타지 않는다.
    missing = missing_required_fields(patient_data)
    if missing:
        return {name: _insufficient_prediction(name, missing) for name in all_models}

    features = patient_to_features(patient_data)

    result = {}
    for name in all_models:
        result[name] = predict_single(name, features)

    # v2.1.6 — C-peptide 미세혈관 신호는 score/level 에 섞지 않고 clinical_flags 로만 표시.
    # v2.1.9 (감사 H2): 실패를 조용히 삼키지 않는다 — 안전망 미적용을 예측에 표면화.
    try:
        cpep_bidirectional_adjust(result, patient_data.get("c_peptide"))
    except Exception as e:
        logger.error("[SAFETY] cpep_bidirectional_adjust 실패: %s", e)
        for info in result.values():
            if isinstance(info, dict) and info.get("available"):
                info.setdefault("warnings", []).append("cpep_flag_unavailable")

    # v2.1.4 — 강한 임상 안전망(HbA1c ≥ 11%)만 마지막에 최소 등급 보장.
    # 이 단계 실패 = HbA1c≥11 고위험 등 안전망 미적용 → 위험도 과소표시 가능 → 반드시 표면화.
    try:
        apply_clinical_floor(result, patient_data, enabled_rules=enabled_rules)
    except Exception as e:
        logger.error("[SAFETY] apply_clinical_floor 실패 — 임상 안전망 미적용: %s", e)
        for info in result.values():
            if isinstance(info, dict) and info.get("available"):
                info.setdefault("warnings", []).append("clinical_safety_net_unavailable")

    # v2.2.2 (H1): floor 로 level 승격된 합병증의 display_score 를 밴드 하한까지 올려
    #   "고위험 배지 + 짧은 바" 모순 제거. raw_score/score 는 ML 원본 유지(불변).
    floor_age = _as_float(patient_data.get("age")) or features.get("age")
    for name, info in result.items():
        if isinstance(info, dict) and info.get("available") and info.get("score") is not None:
            info["display_score"] = _floor_band_score(
                info["score"], info.get("level"), name, age=floor_age
            )

    # KNHANES 코호트 대비 percentile (동일 연령대) — 부가 정보, 실패해도 예측엔 영향 없음.
    try:
        from services.percentile import enrich_predictions
        age = patient_data.get("age") or features.get("age")
        enrich_predictions(result, age)
    except Exception as e:
        logger.warning("[INFO] percentile enrichment 실패 (부가정보): %s", e)

    return result


def predict_with_simulation(
    patient_data: dict,
    c_peptide: float,
    hba1c: float,
    enabled_rules=None,
) -> dict:
    """
    c_peptide, hba1c 값을 오버라이드하여 재예측.

    v2.0.3 — 슬라이더 변화가 ML 출력에 더 잘 반영되도록 다음을 함께 갱신:
      - fbg (공복혈당): 슬라이더 HbA1c 에 맞춰 갱신 (아래 v2.3.0 규칙)
        glu / HOMA_IR / TyG_index / HOMA_beta / BMI_HOMA_IR 가 슬라이더 따라 움직임.
      - he_insulin: c_peptide × 3.0 (구 모델 호환용 저장)

    v2.3.0 (감사): 이전엔 실측 fbg 를 무조건 18×HbA1c 로 덮어써, 슬라이더를 환자
    현재값에 둔 채 시뮬레이션해도 predict_all(실측 fbg) 결과와 어긋났다
    (Dashboard ↔ RiskAnalysis 기준 위험도 불일치). 이제:
      - 실측 fbg + 실측 HbA1c 가 있으면 ADAG eAG(28.7×A1c−46.7) 비율로 실측 fbg 를
        스케일 → 슬라이더 = 현재값이면 fbg 도 실측값 그대로 (baseline 일치).
      - 실측이 없으면 ADAG eAG 공식으로 직접 추정 (구 18×A1c 근사보다 정확).
    """
    modified = dict(patient_data)
    modified["c_peptide"] = c_peptide
    modified["hba1c"] = hba1c

    def _eag(a1c: float) -> float:
        # ADAG(2008): eAG(mg/dL) = 28.7 × HbA1c − 46.7
        return 28.7 * a1c - 46.7

    base_hba1c = _safe_num(patient_data.get("hba1c"), None)
    base_fbg = _safe_num(patient_data.get("fbg"), None)
    if base_fbg is not None and base_fbg > 0 and base_hba1c is not None and _eag(base_hba1c) > 0:
        est_fbg = base_fbg * (_eag(hba1c) / _eag(base_hba1c))
    else:
        est_fbg = _eag(hba1c)
    # 비율 스케일이 모순 입력(예: HbA1c 5.0 + FBG 600)에서 폭증하지 않도록 상·하한을
    # 시뮬레이션 HbA1c 의 eAG 주변으로 묶는다. 그 위에 생리적 절대 범위도 적용.
    eag_target = max(70.0, _eag(hba1c))
    est_fbg = min(max(est_fbg, eag_target * 0.6), eag_target * 1.6)
    modified["fbg"] = min(500.0, max(70.0, est_fbg))

    # v2.2 모델은 C_peptide 단위 학습이지만, 다른 파생경로 호환을 위해
    # he_insulin 동기화 (모델 입력 시점에는 patient_to_features 가 c_peptide 우선 사용).
    modified["he_insulin"] = c_peptide * 3.0
    return predict_all(modified, enabled_rules=enabled_rules)
