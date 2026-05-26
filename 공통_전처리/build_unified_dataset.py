"""
DangBom 프로젝트 — 통일 변수 데이터셋 생성기
==============================================
망막병증 build_model_v3.py 의 41개 변수 정의를 기준으로,
신장질환·심혈관 모델용 데이터셋을 KNHANES 원시 .sav 파일에서 직접 생성한다.

사용법:
  python build_unified_dataset.py

출력:
  - 신장질환/unified_dkd_development.csv / unified_dkd_validation.csv
  - 심혈관/unified_cvd_development.csv / unified_cvd_validation.csv
"""

from __future__ import annotations
import sys
from pathlib import Path

import pyreadstat
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# ── 경로 설정 ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "원시데이터"

# 사용할 연도 (신장질환·심혈관: 2019-2024)
YEARS_FILES = [
    (2019, "HN19_ALL.sav"),
    (2020, "HN20_ALL.sav"),
    (2021, "HN21_ALL.sav"),
    (2022, "HN22_ALL.sav"),
    (2023, "HN23_ALL.sav"),
    (2024, "HN24_ALL.sav"),
]

RANDOM_STATE = 42


# ══════════════════════════════════════════════════════════════
# 1. 원시 데이터 로드
# ══════════════════════════════════════════════════════════════
def load_raw_data(years_files: list[tuple[int, str]]) -> pd.DataFrame:
    """KNHANES .sav 파일을 로드하고 통합한다."""
    dfs = []
    for year, fname in years_files:
        fpath = RAW_DIR / fname
        if not fpath.exists():
            print(f"  [WARN] {fpath} 없음 — 건너뜀")
            continue
        df, _ = pyreadstat.read_sav(str(fpath))
        df["survey_year"] = year
        dfs.append(df)
        print(f"  {year}: {df.shape[0]}명, {df.shape[1]}개 변수")
    all_data = pd.concat(dfs, ignore_index=True)
    print(f"  전체: {all_data.shape[0]}명")
    return all_data


# ══════════════════════════════════════════════════════════════
# 2. 당뇨 환자 필터링
# ══════════════════════════════════════════════════════════════
def filter_dm_patients(df: pd.DataFrame) -> pd.DataFrame:
    """당뇨 환자 필터: DE1_dg==1 or HbA1c>=6.5 or glu>=126"""
    mask = (
        (df["DE1_dg"] == 1.0)
        | (df["HE_HbA1c"] >= 6.5)
        | (df["HE_glu"] >= 126)
    )
    dm = df[mask].copy()
    print(f"  당뇨 환자: {len(dm)}명")
    return dm


# ══════════════════════════════════════════════════════════════
# 3. 통일 41개 변수 엔지니어링
#    (망막병증 build_model_v3.py 로직 그대로)
# ══════════════════════════════════════════════════════════════
def engineer_unified_features(df: pd.DataFrame) -> pd.DataFrame:
    """41개 통일 변수 생성. 입력: 당뇨 환자 DataFrame (KNHANES 원본 컬럼)."""
    out = pd.DataFrame(index=df.index)

    # ── 인구통계 ──
    out["age"] = df["age"]
    out["sex"] = df["sex"]

    # ── 당뇨 관련 ──
    diag_age = df["DE1_ag"].copy()
    diag_age[diag_age >= 888] = np.nan
    out["DM_diagnosis_age"] = diag_age
    out["DM_duration"] = df["age"] - diag_age
    out.loc[out["DM_duration"] < 0, "DM_duration"] = np.nan

    # ── 혈당 지표 ──
    out["HE_glu"] = df["HE_glu"]
    out["HE_HbA1c"] = df["HE_HbA1c"]
    out["HE_insulin"] = df["HE_insulin"]

    # ── 인슐린 저항성 (파생) ──
    out["HOMA_IR"] = (df["HE_glu"] * df["HE_insulin"]) / 405.0
    out["HOMA_beta"] = np.where(
        df["HE_glu"] > 63,
        (360 * df["HE_insulin"]) / (df["HE_glu"] - 63),
        np.nan,
    )
    out["TyG_index"] = np.log(df["HE_TG"] * df["HE_glu"] / 2.0)
    out["BMI_HOMA_IR"] = df["HE_BMI"] * out["HOMA_IR"]

    # ── 지질 검사 ──
    out["HE_chol"] = df["HE_chol"]
    out["HE_HDL_st2"] = df["HE_HDL_st2"]
    out["HE_TG"] = df["HE_TG"]
    out["LDL_calc"] = df["HE_chol"] - df["HE_HDL_st2"] - df["HE_TG"] / 5.0
    out["non_HDL"] = df["HE_chol"] - df["HE_HDL_st2"]

    # ── 신장 기능 ──
    out["HE_crea"] = df["HE_crea"]
    out["HE_BUN"] = df.get("HE_BUN", pd.Series(np.nan, index=df.index))
    out["eGFR"] = df.apply(_calc_egfr, axis=1)
    out["HE_Ualb"] = df.get("HE_Ualb", pd.Series(np.nan, index=df.index))
    ucrea = df.get("HE_Ucrea", pd.Series(np.nan, index=df.index)).replace(0, np.nan)
    out["ACR"] = out["HE_Ualb"] / ucrea

    # ── 혈압 (2·3회 평균, 결측 시 1회) ──
    out["SBP"] = df[["HE_sbp2", "HE_sbp3"]].mean(axis=1)
    out.loc[out["SBP"].isna(), "SBP"] = df.loc[out["SBP"].isna(), "HE_sbp1"]
    out["DBP"] = df[["HE_dbp2", "HE_dbp3"]].mean(axis=1)
    out.loc[out["DBP"].isna(), "DBP"] = df.loc[out["DBP"].isna(), "HE_dbp1"]
    out["pulse_pressure"] = out["SBP"] - out["DBP"]

    # ── 신체 계측 ──
    out["HE_BMI"] = df["HE_BMI"]
    out["HE_ht"] = df["HE_ht"]
    out["HE_wt"] = df["HE_wt"]
    out["HE_wc"] = df["HE_wc"]

    # ── 혈액 검사 ──
    out["HE_HB"] = df["HE_HB"]
    out["HE_WBC"] = df["HE_WBC"]
    out["HE_RBC"] = df["HE_RBC"]
    out["HE_ast"] = df["HE_ast"]
    out["HE_alt"] = df["HE_alt"]

    # ── 소변 검사 이진화 (>=2 → 양성) ──
    for uvar in ["HE_Upro", "HE_Uglu", "HE_Ubld"]:
        col = f"{uvar}_pos"
        if uvar in df.columns:
            out[col] = (df[uvar] >= 2).astype(float)
            out.loc[df[uvar].isna(), col] = np.nan
        else:
            out[col] = np.nan

    # ── 과거력 / 생활습관 (이진) ──
    out["hypertension"] = (df["DI1_dg"] == 1.0).astype(float)
    out["dyslipidemia"] = (df["DI3_dg"] == 1.0).astype(float)
    out["smoking"] = (df["sm_presnt"] == 1.0).astype(float)
    out["drinking"] = (df["dr_month"] == 1.0).astype(float)
    out["exercise"] = (df["pa_aerobic"] == 1.0).astype(float)

    return out


def _calc_egfr(row):
    """CKD-EPI 공식으로 eGFR 계산."""
    scr = row.get("HE_crea")
    age = row.get("age")
    sex = row.get("sex")
    if pd.isna(scr) or pd.isna(age) or pd.isna(sex):
        return np.nan
    if sex == 1:  # 남성
        kappa, alpha, factor = 0.9, -0.411, 1.0
    else:  # 여성
        kappa, alpha, factor = 0.7, -0.329, 1.018
    return (
        141
        * (min(scr / kappa, 1) ** alpha)
        * (max(scr / kappa, 1) ** -1.209)
        * (0.993 ** age)
        * factor
    )


# ══════════════════════════════════════════════════════════════
# 4. 타겟 변수 정의
# ══════════════════════════════════════════════════════════════
def add_target_dkd(features: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """신장질환 타겟: 검사기반 eGFR < 60 (CKD stage 3+)"""
    # eGFR은 이미 features에 파생 계산되어 있음
    egfr = features["eGFR"]
    target = (egfr < 60).astype(float)
    target[egfr.isna()] = np.nan
    features = features.copy()
    features["target_dkd"] = target.values
    return features.dropna(subset=["target_dkd"])


def add_target_cvd(features: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """심혈관 타겟: DI4_dg==1 (심근경색/협심증) 또는 DI5_dg==1 (뇌졸중)"""
    cvd_cols = ["DI4_dg", "DI5_dg"]
    available = [c for c in cvd_cols if c in raw.columns]
    if not available:
        print(f"  [WARN] CVD 타겟 컬럼 없음: {cvd_cols}")
        return pd.DataFrame()

    # DI4_dg, DI5_dg: 0=없음, 1=있음, 8=모름/해당없음
    # 1이면 양성, 0이면 음성, 8/9/NaN이면 제외
    target = pd.Series(np.nan, index=raw.index)
    for col in available:
        target[(raw[col] == 1.0)] = 1.0
    # 양성이 아니면서, 적어도 하나의 컬럼이 0인 경우만 음성으로
    has_zero = False
    for col in available:
        has_zero = has_zero | (raw[col] == 0.0)
    target[(target.isna()) & has_zero] = 0.0

    features = features.copy()
    features["target_cvd"] = target.values
    return features.dropna(subset=["target_cvd"])


# ══════════════════════════════════════════════════════════════
# 5. 핵심 변수 결측 필터링 + Train/Val 분할
# ══════════════════════════════════════════════════════════════
UNIFIED_41_FEATURES = [
    "age", "sex",
    "DM_duration", "DM_diagnosis_age",
    "HE_glu", "HE_HbA1c", "HE_insulin",
    "HOMA_IR", "HOMA_beta", "TyG_index", "BMI_HOMA_IR",
    "HE_chol", "HE_HDL_st2", "HE_TG", "LDL_calc", "non_HDL",
    "HE_crea", "HE_BUN", "eGFR", "HE_Ualb", "ACR",
    "SBP", "DBP", "pulse_pressure",
    "HE_BMI", "HE_ht", "HE_wt", "HE_wc",
    "HE_HB", "HE_WBC", "HE_RBC", "HE_ast", "HE_alt",
    "HE_Upro_pos", "HE_Uglu_pos", "HE_Ubld_pos",
    "hypertension", "dyslipidemia", "smoking", "drinking", "exercise",
]


def prepare_dataset(
    df: pd.DataFrame,
    target_col: str,
    core_vars: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """핵심 변수 결측 제거 후 8:2 stratified split."""
    if core_vars is None:
        core_vars = ["HE_glu", "HE_HbA1c"]

    feature_cols = [c for c in UNIFIED_41_FEATURES if c in df.columns]
    data = df[feature_cols + [target_col]].copy()

    # 핵심 변수 결측 제거
    valid = data[core_vars].notna().all(axis=1)
    data = data[valid]
    print(f"  핵심 변수 결측 제거 후: {len(data)}명")

    y = data[target_col]
    print(f"  양성: {int(y.sum())}명 ({y.mean()*100:.1f}%)")
    print(f"  음성: {int((y==0).sum())}명")

    # 결측률 50% 초과 변수 제거
    missing_pct = data[feature_cols].isnull().mean() * 100
    drop_vars = missing_pct[missing_pct > 50].index.tolist()
    if drop_vars:
        print(f"  결측률 50% 초과 제거: {drop_vars}")
        data = data.drop(columns=drop_vars)
        feature_cols = [c for c in feature_cols if c not in drop_vars]

    print(f"  최종 변수 수: {len(feature_cols)}")

    dev, val = train_test_split(
        data, test_size=0.2, random_state=RANDOM_STATE, stratify=data[target_col]
    )
    print(f"  Development: {len(dev)}명, Validation: {len(val)}명")
    return dev, val


# ══════════════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("DangBom 통일 변수 데이터셋 생성기")
    print("  망막병증 41개 변수 기준, 원시데이터(.sav) 직접 사용")
    print("=" * 70)

    # 1) 원시 데이터 로드
    print("\n[1] 원시 데이터 로드 (2019-2024)")
    raw = load_raw_data(YEARS_FILES)

    # 2) 당뇨 환자 필터링
    print("\n[2] 당뇨 환자 필터링")
    dm = filter_dm_patients(raw)

    # 3) 41개 통일 변수 생성
    print("\n[3] 41개 통일 변수 엔지니어링")
    features = engineer_unified_features(dm)
    print(f"  생성된 변수: {features.shape[1]}개")

    # 4) 신장질환 데이터셋
    print("\n[4] 신장질환(DKD) 데이터셋 생성")
    dkd_data = add_target_dkd(features, dm)
    if len(dkd_data) > 0:
        dkd_dev, dkd_val = prepare_dataset(dkd_data, "target_dkd")
        out_dir = PROJECT_ROOT / "신장질환"
        dkd_dev.to_csv(out_dir / "unified_dkd_development.csv", index=False)
        dkd_val.to_csv(out_dir / "unified_dkd_validation.csv", index=False)
        print(f"  저장: {out_dir / 'unified_dkd_development.csv'}")
        print(f"  저장: {out_dir / 'unified_dkd_validation.csv'}")
    else:
        print("  [ERROR] DKD 데이터 없음")

    # 5) 심혈관 데이터셋
    print("\n[5] 심혈관(CVD) 데이터셋 생성")
    cvd_data = add_target_cvd(features, dm)
    if len(cvd_data) > 0:
        cvd_dev, cvd_val = prepare_dataset(cvd_data, "target_cvd")
        out_dir = PROJECT_ROOT / "심혈관"
        cvd_dev.to_csv(out_dir / "unified_cvd_development.csv", index=False)
        cvd_val.to_csv(out_dir / "unified_cvd_validation.csv", index=False)
        print(f"  저장: {out_dir / 'unified_cvd_development.csv'}")
        print(f"  저장: {out_dir / 'unified_cvd_validation.csv'}")
    else:
        print("  [ERROR] CVD 데이터 없음")

    print("\n" + "=" * 70)
    print("데이터셋 생성 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
