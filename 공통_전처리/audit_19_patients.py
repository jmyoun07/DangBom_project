"""
Audit DB-care predictions for the 19-clinic-patient CSV.

Outputs:
  - C:/DangBom_project/공통_전처리/audit_19_patients_results.csv
  - C:/DangBom_project/공통_전처리/audit_19_patients_report.md

The script intentionally uses the backend predictor objects and the same
patient_to_features()/predict path, then adds model-threshold and local
feature-impact diagnostics for clinical review.
"""
from __future__ import annotations

import math
import sys
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X has feature names")

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from ml import predictor  # noqa: E402
from services.derived import compute_derived  # noqa: E402


INPUT_CSV = ROOT / "병원_데이터_양식 (1)_민 수정.csv"
OUT_CSV = Path(__file__).with_name("audit_19_patients_results.csv")
OUT_MD = Path(__file__).with_name("audit_19_patients_report.md")

MODEL_NAMES = ["retinopathy", "kidney_disease", "cardiovascular"]
MODEL_LABELS = {
    "retinopathy": "망막병증",
    "kidney_disease": "신장질환",
    "cardiovascular": "심혈관",
}

CSV_COLUMN_MAP = {
    "name": "name",
    "chart_no": "chart_no",
    "phone": "phone",
    "dob": "dob",
    "exam_date": "exam_date",
    "sex": "sex",
    "DM_diagnosis_age": "dm_diagnosis_age",
    "dm_medication": "dm_medication",
    "insulin_medication": "insulin_medication",
    "HE_glu": "fbg",
    "HE_HbA1c": "hba1c",
    "c_peptide": "c_peptide",
    "HE_ast": "ast",
    "HE_alt": "alt",
    "HE_crea": "cr",
    "HE_chol": "total_cholesterol",
    "HE_TG": "triglycerides",
    "HE_HDL_st2": "hdl",
    "LDL": "ldl",
    "SBP": "sbp",
    "DBP": "dbp",
    "HE_ht": "height",
    "HE_wt": "weight",
    "HE_Upro": "he_upro",
    "HE_Uglu": "he_uglu",
    "HE_Ubld": "he_ubld",
    "urine_bil": "urine_bil",
    "urine_uro": "urine_uro",
    "urine_ket": "urine_ket",
    "urine_nit": "urine_nit",
    "urine_ph": "urine_ph",
    "urine_sg": "urine_sg",
    "smoking": "smoking",
    "drinking": "drinking",
    "exercise": "exercise",
    "sleep_hours": "sleep_hours",
}

STRING_FIELDS = {"name", "chart_no", "phone", "sex"}


def parse_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def coerce_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and pd.isna(value):
            return None
        return float(value)
    s = str(value).strip().replace("\u3000", "").replace(",", "")
    if not s:
        return None
    if s.lower() in {"-", "--", "n/a", "na", "nan", "null", "#null!"}:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if len(nums) == 2:
            return nums[0] + nums[1] / 60.0
        if len(nums) == 3:
            return nums[0] + nums[1] / 60.0 + nums[2] / 3600.0
    try:
        return float(s)
    except ValueError:
        return None


def row_to_patient_data(row: pd.Series, idx: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for csv_col, db_field in CSV_COLUMN_MAP.items():
        if csv_col not in row:
            continue
        val = row[csv_col]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        if db_field in {"exam_date", "dob"}:
            parsed = parse_date(val)
            if parsed is not None:
                out[db_field] = parsed
        elif db_field in STRING_FIELDS:
            s = str(val).strip()
            if s:
                out[db_field] = s
        else:
            num = coerce_numeric(val)
            if num is not None:
                out[db_field] = num

    if not str(out.get("name", "")).strip():
        out["name"] = f"patient_{idx + 1}"
    if "exam_date" not in out:
        out["exam_date"] = date.today()

    if out.get("sex") in [1, 1.0, "1"]:
        out["sex"] = "M"
    elif out.get("sex") in [2, 2.0, "2"]:
        out["sex"] = "F"

    return compute_derived(out)


def transform_for_pkg(pkg: dict, features: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    model_features = pkg["features"]
    raw = pd.DataFrame([features])
    for col in model_features:
        if col not in raw.columns:
            raw[col] = np.nan
    raw = raw[model_features]

    x = raw.copy()
    if pkg.get("imputer") is not None:
        x = pd.DataFrame(pkg["imputer"].transform(x), columns=model_features)
    if pkg.get("scaler") is not None:
        x = pd.DataFrame(pkg["scaler"].transform(x), columns=model_features)
    return raw, x


def proba_from_raw(pkg: dict, raw: pd.DataFrame) -> float:
    x = raw.copy()
    model_features = pkg["features"]
    if pkg.get("imputer") is not None:
        x = pd.DataFrame(pkg["imputer"].transform(x), columns=model_features)
    if pkg.get("scaler") is not None:
        x = pd.DataFrame(pkg["scaler"].transform(x), columns=model_features)
    return predictor._predict_proba_from_pkg(pkg, x)


def level_common(score: float) -> str:
    if score >= 60:
        return "고위험"
    if score >= 30:
        return "중위험"
    return "저위험"


def level_model_threshold(model_name: str, proba: float) -> str:
    pkg = predictor._load_model(model_name)
    threshold = float(pkg.get("threshold") or 0.30)
    # The persisted model threshold is a positive/negative decision threshold.
    # Use it as a clinical "medium-or-higher" floor, with 60% still high.
    if proba >= 0.60:
        return "고위험"
    if proba >= threshold:
        return "중위험"
    return "저위험"


def clinical_floor(patient: dict, current_level: str) -> tuple[str, list[str]]:
    score = {"저위험": 0, "중위험": 1, "고위험": 2}
    target = current_level
    reasons: list[str] = []

    hba1c = patient.get("hba1c")
    cpep = patient.get("c_peptide")
    dur = patient.get("dm_duration")

    if hba1c is not None and hba1c >= 9.0:
        target = "중위험" if score[target] < 1 else target
        reasons.append("HbA1c >= 9.0")
    if hba1c is not None and hba1c >= 11.0:
        target = "고위험" if score[target] < 2 else target
        reasons.append("HbA1c >= 11.0")
    if cpep is not None and cpep < 0.5:
        target = "중위험" if score[target] < 1 else target
        reasons.append("C-peptide < 0.5")
    if hba1c is not None and cpep is not None and hba1c >= 8.0 and cpep < 0.7:
        target = "중위험" if score[target] < 1 else target
        reasons.append("HbA1c >= 8.0 and C-peptide < 0.7")
    if hba1c is not None and dur is not None and hba1c >= 8.5 and dur >= 10:
        target = "중위험" if score[target] < 1 else target
        reasons.append("HbA1c >= 8.5 and DM duration >= 10y")

    return target, reasons


def local_feature_impacts(model_name: str, features: dict, top_n: int = 8) -> tuple[float, list[tuple[str, float, Any, Any]]]:
    pkg = predictor._load_model(model_name)
    raw, _ = transform_for_pkg(pkg, features)
    base = proba_from_raw(pkg, raw)
    model_features = pkg["features"]

    if pkg.get("imputer") is not None and hasattr(pkg["imputer"], "statistics_"):
        refs = dict(zip(model_features, pkg["imputer"].statistics_))
    else:
        refs = {col: np.nan for col in model_features}

    impacts = []
    for col in model_features:
        ref = refs.get(col)
        current = raw.at[0, col]
        if pd.isna(current) and pd.isna(ref):
            continue
        modified = raw.copy()
        modified.at[0, col] = ref
        try:
            changed = proba_from_raw(pkg, modified)
        except Exception:
            continue
        delta_points = (base - changed) * 100.0
        impacts.append((col, round(delta_points, 2), current, ref))

    impacts.sort(key=lambda x: abs(x[1]), reverse=True)
    return base, impacts[:top_n]


def global_importance(model_name: str, top_n: int = 8) -> list[tuple[str, float]]:
    pkg = predictor._load_model(model_name)
    feats = pkg["features"]
    values = None
    if pkg.get("model") is not None and hasattr(pkg["model"], "feature_importances_"):
        values = np.asarray(pkg["model"].feature_importances_, dtype=float)
    elif pkg.get("model_type") == "Stacking" and "stacking" in pkg:
        arrays = []
        for model in pkg["stacking"].get("base_models", {}).values():
            if hasattr(model, "feature_importances_"):
                arr = np.asarray(model.feature_importances_, dtype=float)
                if len(arr) == len(feats):
                    arrays.append(arr)
        if arrays:
            values = np.mean(arrays, axis=0)
    if values is None or len(values) != len(feats):
        return []
    total = float(np.sum(np.abs(values))) or 1.0
    pairs = [(f, round(float(v) / total * 100.0, 2)) for f, v in zip(feats, values)]
    return sorted(pairs, key=lambda x: abs(x[1]), reverse=True)[:top_n]


def fmt_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def main() -> None:
    df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    patients = [row_to_patient_data(row, i) for i, row in df.iterrows()]

    records: list[dict[str, Any]] = []
    impact_by_patient: dict[str, dict[str, list[tuple[str, float, Any, Any]]]] = {}

    for pdata in patients:
        features = predictor.patient_to_features(pdata)
        preds = predictor.predict_all(pdata)
        row: dict[str, Any] = {
            "chart_no": pdata.get("chart_no"),
            "name": pdata.get("name"),
            "sex": pdata.get("sex"),
            "age": pdata.get("age"),
            "dm_duration": pdata.get("dm_duration"),
            "hba1c": pdata.get("hba1c"),
            "c_peptide": pdata.get("c_peptide"),
            "fbg": pdata.get("fbg"),
            "cr": pdata.get("cr"),
            "egfr": pdata.get("egfr"),
            "sbp": pdata.get("sbp"),
            "dbp": pdata.get("dbp"),
        }

        levels = []
        threshold_levels = []
        impact_by_patient[str(pdata.get("chart_no"))] = {}
        for model_name in MODEL_NAMES:
            pred = preds[model_name]
            proba, impacts = local_feature_impacts(model_name, features)
            impact_by_patient[str(pdata.get("chart_no"))][model_name] = impacts
            score = round(proba * 100, 1)
            common = level_common(score)
            threshold_level = level_model_threshold(model_name, proba)
            levels.append(common)
            threshold_levels.append(threshold_level)
            prefix = model_name
            row[f"{prefix}_score"] = score
            row[f"{prefix}_level_common_30_60"] = common
            row[f"{prefix}_threshold"] = round(float(predictor._load_model(model_name).get("threshold", 0.3)) * 100, 1)
            row[f"{prefix}_level_model_threshold"] = threshold_level
            row[f"{prefix}_top_risk_drivers"] = "; ".join(
                f"{name}:{delta:+.2f}p" for name, delta, _, _ in impacts[:5] if delta > 0
            )
            row[f"{prefix}_top_protective_drivers"] = "; ".join(
                f"{name}:{delta:+.2f}p" for name, delta, _, _ in impacts[:5] if delta < 0
            )

        highest = "고위험" if "고위험" in levels else ("중위험" if "중위험" in levels else "저위험")
        threshold_highest = (
            "고위험" if "고위험" in threshold_levels else ("중위험" if "중위험" in threshold_levels else "저위험")
        )
        floored, floor_reasons = clinical_floor(pdata, highest)
        row["overall_level_common_30_60"] = highest
        row["overall_level_model_threshold"] = threshold_highest
        row["overall_level_with_clinical_floor"] = floored
        row["clinical_floor_reasons"] = "; ".join(floor_reasons)
        records.append(row)

    out = pd.DataFrame(records)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    low = out[out["overall_level_common_30_60"] == "저위험"]
    flagged = out[out["clinical_floor_reasons"].astype(str) != ""]
    targets = out[out["chart_no"].isin(["D3005", "D2867", "D2862"])]

    lines: list[str] = []
    lines.append("# DB-care 19명 환자 ML 감사 결과")
    lines.append("")
    lines.append(f"- 입력: `{INPUT_CSV}`")
    lines.append(f"- 상세 CSV: `{OUT_CSV}`")
    lines.append(f"- 전체 {len(out)}명 중 현행 공통 30/60 컷오프 기준 저위험: {len(low)}명")
    lines.append(f"- 임상 안전망 룰 적용 시 상향 필요: {len(flagged)}명")
    lines.append("")
    lines.append("## 모델 임계값")
    lines.append("")
    lines.append("| 모델 | 저장 threshold | 현행 등급 컷오프 | 관찰 |")
    lines.append("|---|---:|---:|---|")
    for m in MODEL_NAMES:
        pkg = predictor._load_model(m)
        lines.append(
            f"| {MODEL_LABELS[m]} | {float(pkg.get('threshold')) * 100:.1f}% | 30%/60% | "
            "저장 threshold는 predict_single/_classify_risk에서 사용되지 않음 |"
        )
    lines.append("")
    lines.append("## 의료진 지적 3명")
    lines.append("")
    lines.append("| 차트 | 이름 | HbA1c | C-pep | 유병 | 현행 전체 | threshold 전체 | 안전망 후 | 점수(망막/신장/심혈관) | 안전망 사유 |")
    lines.append("|---|---|---:|---:|---:|---|---|---|---|---|")
    for _, r in targets.iterrows():
        scores = f"{r.retinopathy_score:.1f}/{r.kidney_disease_score:.1f}/{r.cardiovascular_score:.1f}"
        lines.append(
            f"| {r.chart_no} | {r['name']} | {r.hba1c:.1f} | {r.c_peptide:.2f} | {int(r.dm_duration)} | "
            f"{r.overall_level_common_30_60} | {r.overall_level_model_threshold} | "
            f"{r.overall_level_with_clinical_floor} | {scores} | {r.clinical_floor_reasons} |"
        )
    lines.append("")
    lines.append("## 현행 저위험 환자")
    lines.append("")
    lines.append("| 차트 | 이름 | HbA1c | C-pep | 유병 | 망막 | 신장 | 심혈관 | 안전망 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for _, r in low.iterrows():
        lines.append(
            f"| {r.chart_no} | {r['name']} | {r.hba1c:.1f} | {r.c_peptide:.2f} | {int(r.dm_duration)} | "
            f"{r.retinopathy_score:.1f} | {r.kidney_disease_score:.1f} | {r.cardiovascular_score:.1f} | "
            f"{r.overall_level_with_clinical_floor} ({r.clinical_floor_reasons}) |"
        )
    lines.append("")
    lines.append("## 의료진 지적 3명 로컬 영향도")
    lines.append("")
    lines.append("양수는 해당 환자 점수를 올린 변수, 음수는 낮춘 변수입니다. 기준값은 모델 imputer의 학습 중앙/최빈값입니다.")
    for _, r in targets.iterrows():
        chart = str(r.chart_no)
        lines.append("")
        lines.append(f"### {chart} {r['name']}")
        for m in MODEL_NAMES:
            impacts = impact_by_patient[chart][m]
            text = ", ".join(
                f"{feat} {delta:+.2f}p({fmt_value(cur)} -> ref {fmt_value(ref)})"
                for feat, delta, cur, ref in impacts[:8]
            )
            lines.append(f"- {MODEL_LABELS[m]}: {text}")
    lines.append("")
    lines.append("## 전역 feature_importances 상위")
    for m in MODEL_NAMES:
        lines.append("")
        lines.append(f"### {MODEL_LABELS[m]}")
        imp = global_importance(m)
        lines.append(", ".join(f"{f} {v:.2f}%" for f, v in imp) if imp else "사용 가능한 feature_importances 없음")
    lines.append("")
    lines.append("## 핵심 결론")
    lines.append("")
    lines.append("1. 현행 등급화는 모델별 학습 threshold를 무시하고 score 30/60만 사용합니다.")
    lines.append("2. 망막병증은 저장 threshold가 약 19.5%라서 20~29점 환자가 임계값상 양성인데도 화면에서는 저위험이 됩니다.")
    lines.append("3. DKD/CVD 모델은 C_peptide를 직접 feature로 쓰지 않고 TyG만 쓰므로 저 C-peptide 위험을 구조적으로 반영하지 못합니다.")
    lines.append("4. 저 C-peptide + 고 HbA1c + 긴 유병기간 조합은 ML 후처리 임상 안전망 룰로 최소 중위험 이상 보정해야 합니다.")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(out[[
        "chart_no", "name", "hba1c", "c_peptide", "dm_duration",
        "retinopathy_score", "kidney_disease_score", "cardiovascular_score",
        "overall_level_common_30_60", "overall_level_model_threshold",
        "overall_level_with_clinical_floor", "clinical_floor_reasons",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
