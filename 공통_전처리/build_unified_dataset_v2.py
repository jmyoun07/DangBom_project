"""
통일 데이터셋 빌더 v2.2 — C-peptide 기반 재학습용
=============================================

병원 호환을 위해 KNHANES 의 HE_insulin (µU/mL) 을 C-peptide (ng/mL) 로 변환해 사용.
  - 변환식: C_peptide = HE_insulin / 3.0  (임상적 근사, 병원 C-peptide × 3.0 ≈ insulin 의 역변환)
  - HOMA_IR, HOMA_beta, BMI_HOMA_IR 모두 C_peptide 값으로 재계산
  - 기존 HE_insulin 컬럼은 C_peptide 로 대체 (feature name 변경)

질환별로 다른 연도/변수 집합을 사용하여 샘플 수 극대화.

| 모델 | 연도          | 변수 | 제외 변수 (C-peptide 4종) |
|------|--------------|------|--------------------------|
| DR   | HN19~21       | 42개 | 없음 (C_peptide + HOMA 3종 포함) |
| DKD  | HN19~24       | 38개 | C_peptide, HOMA_IR, HOMA_beta, BMI_HOMA_IR |
| CVD  | HN19~21, HN24 | 38개 | 위와 동일                 |

사유:
  - DR  타겟(DH7_dg/E_DM): HN22+ 에 없음 → 3년만 가능. HE_insulin 보유 → C_peptide 변환.
  - DKD 타겟(DN1_dg):      HN19~24 모두 있음. HE_insulin 은 HN22+ 없음 → C-peptide 4종 제외.
  - CVD 타겟(DI3~DI6_dg):  HN22/23 없음. HN24 있음 → 4년. C-peptide 4종 제외.
"""
import os
import sys
import io
import json
import numpy as np
import pandas as pd
import pyreadstat

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(ROOT, "원시데이터")
OUT_DIRS = {
    "DR":  os.path.join(ROOT, "망막병증"),
    "DKD": os.path.join(ROOT, "신장질환"),
    "CVD": os.path.join(ROOT, "심혈관"),
}
for d in OUT_DIRS.values():
    os.makedirs(d, exist_ok=True)

# 질환별 연도
YEARS_BY_DISEASE = {
    "DR":  [2019, 2020, 2021],
    "DKD": [2019, 2020, 2021, 2022, 2023, 2024],
    "CVD": [2019, 2020, 2021, 2024],
}
FILE_FOR_YEAR = {yr: f"HN{str(yr)[-2:]}_ALL.sav" for yr in range(2019, 2025)}

# C-peptide 4종 (DKD/CVD 에서 제외 — HN22+ 에 HE_insulin 없어 C_peptide 파생 불가)
INSULIN_FEATURES = ["C_peptide", "HOMA_IR", "HOMA_beta", "BMI_HOMA_IR"]

# 공통 feature group (DR 용 — 42개 모두)
FULL_FEATURE_GROUPS = {
    "인구통계":          ["age", "sex"],
    "당뇨 관련":         ["DM_duration", "DM_diagnosis_age", "DM_medication", "insulin_medication"],
    "혈당·C-peptide":     ["HE_glu", "HE_HbA1c", "C_peptide"],
    "인슐린 저항성(파생)": ["HOMA_IR", "HOMA_beta", "TyG_index", "BMI_HOMA_IR"],
    "지질":             ["HE_chol", "HE_HDL_st2", "HE_TG", "LDL_calc", "non_HDL"],
    "신장 기능":         ["HE_crea", "eGFR"],
    "혈압":             ["SBP", "DBP", "pulse_pressure", "hypertension"],
    "신체 계측":         ["HE_BMI", "HE_ht", "HE_wt"],
    "간효소":           ["HE_ast", "HE_alt"],
    "소변(확장)":        [
        "HE_Upro_pos", "HE_Uglu_pos", "HE_Ubld_pos",
        "HE_Ubil_pos", "HE_Uro_abn", "HE_Uket_pos",
        "HE_Unitr_b", "HE_Uph", "HE_Usg",
    ],
    "생활습관":          ["smoking", "drinking", "exercise", "sleep_7h"],
}


def reduced_feature_groups():
    """insulin 4종 제외한 feature groups (DKD/CVD 용, 38개)."""
    out = {}
    for grp, feats in FULL_FEATURE_GROUPS.items():
        filtered = [f for f in feats if f not in INSULIN_FEATURES]
        if filtered:
            out[grp] = filtered
    return out


# ---------------------------------------------------------
# 1. 데이터 로드
# ---------------------------------------------------------
def load_years(years):
    dfs = []
    for year in years:
        path = os.path.join(RAW_DIR, FILE_FOR_YEAR[year])
        df, _ = pyreadstat.read_sav(path)
        df["survey_year"] = year
        dfs.append(df)
        print(f"    {year}: {df.shape[0]:,}명")
    return pd.concat(dfs, ignore_index=True)


# ---------------------------------------------------------
# 2. 당뇨 필터
# ---------------------------------------------------------
def filter_diabetes(df):
    mask = (
        (df["DE1_dg"] == 1.0)
        | (df["HE_HbA1c"] >= 6.5)
        | (df["HE_glu"] >= 126)
    )
    return df[mask].copy()


# ---------------------------------------------------------
# 3. 파생변수 계산
# ---------------------------------------------------------
def _hours_from_clock(row, bh, bm, wh, wm):
    try:
        b_h, b_m, w_h, w_m = row[bh], row[bm], row[wh], row[wm]
        for v in (b_h, b_m, w_h, w_m):
            if pd.isna(v) or v >= 88:
                return np.nan
        bed  = b_h * 60 + b_m
        wake = w_h * 60 + w_m
        if wake <= bed:
            wake += 24 * 60
        h = (wake - bed) / 60.0
        return h if 0 < h < 24 else np.nan
    except (KeyError, TypeError):
        return np.nan


def compute_sleep_hours(row):
    """
    HN16-18: Total_slp_wk/wd (파생 존재)
    HN19/20/22/23: BP16_1, BP16_2 (시간 단위 직접 입력)
    HN21/24: BP16_11~14, BP16_21~24 (시각 → 계산)
    """
    year = row.get("survey_year")
    wk = wd = np.nan
    if year in (2019, 2020, 2022, 2023):
        wk = row.get("BP16_1", np.nan)
        wd = row.get("BP16_2", np.nan)
    elif year in (2021, 2024):
        wk = _hours_from_clock(row, "BP16_11", "BP16_12", "BP16_13", "BP16_14")
        wd = _hours_from_clock(row, "BP16_21", "BP16_22", "BP16_23", "BP16_24")
    elif year in (2016, 2017, 2018):
        wk = row.get("Total_slp_wk", np.nan)
        wd = row.get("Total_slp_wd", np.nan)
    wk = np.nan if (pd.isna(wk) or wk >= 88) else wk
    wd = np.nan if (pd.isna(wd) or wd >= 88) else wd
    if pd.isna(wk) or pd.isna(wd):
        return np.nan
    return (5 * wk + 2 * wd) / 7.0


def calc_egfr(row):
    scr, age, sex = row["HE_crea"], row["age"], row["sex"]
    if pd.isna(scr) or pd.isna(age) or pd.isna(sex) or scr <= 0:
        return np.nan
    if sex == 1:
        kappa, alpha, factor = 0.9, -0.411, 1.0
    else:
        kappa, alpha, factor = 0.7, -0.329, 1.018
    return 141 * (min(scr/kappa, 1) ** alpha) * (max(scr/kappa, 1) ** -1.209) * (0.993 ** age) * factor


def engineer_features(df, include_insulin: bool):
    # 혈압
    df["SBP"] = df[["HE_sbp2", "HE_sbp3"]].mean(axis=1)
    df.loc[df["SBP"].isna(), "SBP"] = df.loc[df["SBP"].isna(), "HE_sbp1"]
    df["DBP"] = df[["HE_dbp2", "HE_dbp3"]].mean(axis=1)
    df.loc[df["DBP"].isna(), "DBP"] = df.loc[df["DBP"].isna(), "HE_dbp1"]

    # 당뇨 이환기간
    df["DM_duration"] = df["age"] - df["DE1_ag"]
    df.loc[df["DE1_ag"] >= 888, "DM_duration"] = np.nan
    df.loc[df["DM_duration"] < 0, "DM_duration"] = np.nan
    df["DM_diagnosis_age"] = df["DE1_ag"].where(df["DE1_ag"] < 888, np.nan)

    # 당뇨약/인슐린 투약 여부 (8=비해당 → 0 처리)
    df["insulin_medication"] = df["DE1_31"].map(
        lambda v: 1.0 if v == 1 else (0.0 if v in (0, 8) else np.nan)
    )
    df["DM_medication"] = df["DE1_32"].map(
        lambda v: 1.0 if v == 1 else (0.0 if v in (0, 8) else np.nan)
    )

    # C-peptide 기반 변수 (HE_insulin 컬럼 존재하는 연도만 유효 — HN19~21)
    # 임상 근사: C_peptide (ng/mL) = HE_insulin (µU/mL) / 3.0
    # HOMA 공식을 C_peptide 값 그대로 사용 (scaler 가 정규화하므로 계수 차이 무관)
    if include_insulin and "HE_insulin" in df.columns:
        df["C_peptide"] = df["HE_insulin"] / 3.0
        df["HOMA_IR"]  = (df["HE_glu"] * df["C_peptide"]) / 405.0
        df["HOMA_beta"] = np.where(
            df["HE_glu"] > 63,
            (360 * df["C_peptide"]) / (df["HE_glu"] - 63),
            np.nan,
        )
        df["BMI_HOMA_IR"] = df["HE_BMI"] * df["HOMA_IR"]

    # 지질 파생
    df["non_HDL"]  = df["HE_chol"] - df["HE_HDL_st2"]
    df["LDL_calc"] = df["HE_chol"] - df["HE_HDL_st2"] - df["HE_TG"] / 5.0

    # TyG_index (insulin 과 무관, glucose·TG 기반 → 모든 연도 가능)
    df["TyG_index"] = np.log(df["HE_TG"] * df["HE_glu"] / 2.0)

    # eGFR
    df["eGFR"] = df.apply(calc_egfr, axis=1)

    # 혈압 파생
    df["pulse_pressure"] = df["SBP"] - df["DBP"]

    # 생활습관/병력
    for src_col, dst_col in [
        ("DI1_dg", "hypertension"),
        ("sm_presnt", "smoking"),
        ("dr_month", "drinking"),
        ("pa_aerobic", "exercise"),
    ]:
        if src_col in df.columns:
            df[dst_col] = (df[src_col] == 1.0).astype(float)
            df.loc[df[src_col].isna(), dst_col] = np.nan
        else:
            df[dst_col] = np.nan

    # 수면
    df["sleep_hours"] = df.apply(compute_sleep_hours, axis=1)
    df["sleep_7h"]    = (df["sleep_hours"] >= 7).astype(float)
    df.loc[df["sleep_hours"].isna(), "sleep_7h"] = np.nan

    # 소변 binary (≥2 양성)
    for uvar in ["HE_Upro", "HE_Uglu", "HE_Ubld", "HE_Ubil", "HE_Uket"]:
        if uvar in df.columns:
            df[f"{uvar}_pos"] = (df[uvar] >= 2).astype(float)
            df.loc[df[uvar].isna(), f"{uvar}_pos"] = np.nan
        else:
            df[f"{uvar}_pos"] = np.nan

    if "HE_Uro" in df.columns:
        df["HE_Uro_abn"] = (df["HE_Uro"] >= 2).astype(float)
        df.loc[df["HE_Uro"].isna(), "HE_Uro_abn"] = np.nan
    else:
        df["HE_Uro_abn"] = np.nan

    if "HE_Unitr" in df.columns:
        df["HE_Unitr_b"] = df["HE_Unitr"].astype(float)
        df.loc[~df["HE_Unitr"].isin([0, 1]), "HE_Unitr_b"] = np.nan
    else:
        df["HE_Unitr_b"] = np.nan

    return df


# ---------------------------------------------------------
# 4. 타겟 정의
# ---------------------------------------------------------
def target_DR(df):
    tgt = np.full(len(df), np.nan)
    tgt[df["DH7_dg"] == 1.0] = 1
    tgt[df["DH7_dg"] == 0.0] = 0
    if "E_DM" in df.columns:
        edm_pos = (df["E_DM"] == 1.0) & pd.isna(tgt)
        edm_neg = (df["E_DM"] == 0.0) & pd.isna(tgt)
        tgt[edm_pos.values] = 1
        tgt[edm_neg.values] = 0
    return tgt


def target_DKD(df):
    tgt = np.full(len(df), np.nan)
    tgt[df["DN1_dg"] == 1.0] = 1
    tgt[df["DN1_dg"] == 0.0] = 0
    return tgt


def target_CVD(df):
    cvd_cols = [c for c in ["DI3_dg", "DI4_dg", "DI5_dg", "DI6_dg"] if c in df.columns]
    if not cvd_cols:
        return np.full(len(df), np.nan)
    any_pos   = (df[cvd_cols] == 1.0).any(axis=1)
    all_known = df[cvd_cols].isin([0.0, 1.0]).all(axis=1)
    tgt = np.full(len(df), np.nan)
    tgt[any_pos.values] = 1
    tgt[(all_known & ~any_pos).values] = 0
    return tgt


# ---------------------------------------------------------
# 5. 질환별 파이프라인
# ---------------------------------------------------------
def build_for_disease(disease_key: str):
    from sklearn.model_selection import train_test_split

    years = YEARS_BY_DISEASE[disease_key]
    include_insulin = (disease_key == "DR")
    feature_groups = FULL_FEATURE_GROUPS if include_insulin else reduced_feature_groups()
    features = [f for grp in feature_groups.values() for f in grp]

    out_dir = OUT_DIRS[disease_key]
    print(f"\n{'=' * 70}")
    print(f"[{disease_key}] 연도={years}, 변수={len(features)}개, insulin={'포함' if include_insulin else '제외'}")
    print("=" * 70)

    print("  데이터 로드:")
    raw = load_years(years)
    print(f"  전체: {len(raw):,}명")

    dm = filter_diabetes(raw)
    print(f"  당뇨 필터링: {len(dm):,}명")

    eng = engineer_features(dm, include_insulin=include_insulin)

    if disease_key == "DR":
        eng["target"] = target_DR(eng)
    elif disease_key == "DKD":
        eng["target"] = target_DKD(eng)
    else:
        eng["target"] = target_CVD(eng)

    sub = eng[eng["target"].notna()].copy()
    sub = sub[sub[["HE_glu", "HE_HbA1c"]].notna().all(axis=1)]

    missing_feats = [f for f in features if f not in sub.columns]
    if missing_feats:
        print(f"  [warn] 누락 변수 — NaN 으로 채움: {missing_feats}")
        for f in missing_feats:
            sub[f] = np.nan

    X = sub[features + ["survey_year", "target"]].copy()
    X["target"] = X["target"].astype(int)
    y = X["target"]

    dev, val = train_test_split(X, test_size=0.2, random_state=42, stratify=y)
    dev.to_csv(os.path.join(out_dir, "development.csv"), index=False, encoding="utf-8-sig")
    val.to_csv(os.path.join(out_dir, "validation.csv"),  index=False, encoding="utf-8-sig")

    summary = {
        "source":   f"KNHANES HN{years[0]%100}~HN{years[-1]%100}",
        "years":    years,
        "target":   disease_key,
        "include_insulin": include_insulin,
        "n_features": len(features),
        "features": features,
        "feature_groups": feature_groups,
        "n_total":   int(len(X)),
        "n_dev":     int(len(dev)),
        "n_val":     int(len(val)),
        "n_dev_pos": int(dev["target"].sum()),
        "n_val_pos": int(val["target"].sum()),
        "prevalence": float(y.mean()),
    }
    with open(os.path.join(out_dir, "dataset_meta.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"  [결과] dev={len(dev):,} (+{int(dev['target'].sum())}) / "
          f"val={len(val):,} (+{int(val['target'].sum())}) — 유병률 {y.mean()*100:.1f}%")
    return summary


if __name__ == "__main__":
    print("=" * 70)
    print("통일 데이터셋 빌더 v2.1 — 질환별 독립 구성")
    print("=" * 70)
    summaries = {}
    for key in ["DR", "DKD", "CVD"]:
        summaries[key] = build_for_disease(key)

    print("\n" + "=" * 70)
    print("완료 — 최종 요약")
    print("=" * 70)
    for key, s in summaries.items():
        print(
            f"  [{key}] 연도 {s['years'][0]}~{s['years'][-1]} | "
            f"변수 {s['n_features']}개 | "
            f"총 {s['n_total']:,}명 (+{s['n_dev_pos']+s['n_val_pos']}) | "
            f"유병률 {s['prevalence']*100:.1f}%"
        )
