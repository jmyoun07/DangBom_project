"""
v2.1.5 안전망 4룰 + C-pep 6단계 flag + 졸업 시나리오 회귀 테스트.

v2.1.4 C3: 개별 합병증 score/level 은 ML raw + model_threshold 로 유지하고,
임상 주의 신호는 clinical_flags 로 분리한다. 종합 risk_level 만 강한 임상 안전망을 적용한다.

v2.1.5 (원장님 5월 18일 답변 §2):
  Rule 1: HbA1c ≥ 11% → 모든 합병증 무조건 고위험 (강화)
  Rule 2: HbA1c ≥ 9%  → 최소 중위험 (신규)
  Rule 3: C-pep < 0.5 → 최소 중위험 (신규)
  Rule 4: 유병 ≥ 10년 AND HbA1c ≥ 8.5 → 최소 중위험 (신규)

실행:
    python C:/DangBom_project/공통_전처리/verify_v213_safety_net.py

산출물:
    C:/DangBom_project/공통_전처리/audit_19_patients_full.csv
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# sklearn fit warnings 억제 (배포 로그 오염 방지 — Codex M5 부분 대응)
warnings.filterwarnings("ignore", message=".*feature names.*fitted without.*")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DBCARE_DESKTOP", "1")

import pandas as pd
from ml.predictor import predict_all

CSV_PATH = ROOT / "병원_데이터_양식 (1)_민 수정.csv"
OUT_CSV = ROOT / "공통_전처리" / "audit_19_patients_full.csv"

# KNHANES 컬럼 → backend 컬럼 매핑
COL_MAP = {
    "HE_HbA1c": "hba1c", "HE_glu": "fbg", "HE_ast": "ast", "HE_alt": "alt",
    "HE_crea": "cr", "HE_chol": "total_cholesterol", "HE_TG": "triglycerides",
    "HE_HDL_st2": "hdl", "HE_ht": "height", "HE_wt": "weight",
    "HE_Upro": "he_upro", "HE_Uglu": "he_uglu", "HE_Ubld": "he_ubld",
    "LDL": "ldl", "SBP": "sbp", "DBP": "dbp",
}

# 의료진 지적 케이스 + 기대 종합 등급 (회귀 assertion)
# v2.1.5: Rule 1 (HbA1c ≥ 11%) 적용 케이스는 EXPECTED_HIGH 로 분리
EXPECTED_HIGH = {
    "D3005": ("권선호", "고위험", "HbA1c 13.9 → Rule 1 (HbA1c ≥ 11%) 무조건 고위험"),
    "D3096": ("김성복", "고위험", "HbA1c 11.2 → Rule 1 (HbA1c ≥ 11%) 무조건 고위험"),
}

EXPECTED_MID = {
    "D2867": ("고승권", "중위험", "HbA1c 9.3 (Rule 2) + C-펩 0.23 (Rule 3) → 중위험 floor"),
    "D2862": ("하정아", "중위험", "C-펩 0.48 (Rule 3) → 중위험 floor"),
    # v2.1.5 신규: HbA1c 정상이라도 C-펩 < 0.5 단독으로 Rule 3 발동
    "D3619": ("장찬호", "중위험", "C-펩 0.48 (Rule 3) → 중위험 floor (이전 v2.1.4 에선 저위험)"),
}

EXPECTED_LOW = {
    "D3593": "박경영",
}

LEVEL_RANK = {"고위험": 3, "중위험": 2, "저위험": 1}
MIN_LOW_COUNT = 5


def load_19():
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    df = df.dropna(axis=1, how="all")
    df = df.rename(columns=COL_MAP)
    df["sex"] = df["sex"].apply(lambda v: "M" if v == 1 else "F")
    # 숫자 컬럼 안전 캐스트
    for col in ("sleep_hours", "smoking", "drinking", "exercise",
                "dm_medication", "insulin_medication", "dm_diagnosis_age",
                "urine_nit"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate_clinical_floor(row) -> tuple[str | None, str | None]:
    """
    환자 종합 risk_level 에만 적용되는 안전망. 개별 합병증 level 은 변경하지 않는다.

    v2.1.5 — 원장님 5월 18일 답변 §2 4룰 정합:
      Rule 1: HbA1c ≥ 11%  → 고위험 (강화, 기존 중위험 → 고위험)
      Rule 2: HbA1c ≥ 9%   → 중위험
      Rule 3: C-pep < 0.5  → 중위험
      Rule 4: 유병 ≥ 10년 + HbA1c ≥ 8.5 → 중위험
    """
    hba1c = _as_float(row.get("hba1c"))
    cpep = _as_float(row.get("c_peptide"))
    dm_dur = _as_float(row.get("DM_duration") if row.get("DM_duration") is not None else row.get("dm_duration"))

    # Rule 1: 가장 강함 — 고위험
    if hba1c is not None and hba1c >= 11.0:
        return "고위험", "aggregate_floor:rule1_hba1c_very_high"
    # Rule 2: HbA1c ≥ 9%
    if hba1c is not None and hba1c >= 9.0:
        return "중위험", "aggregate_floor:rule2_hba1c_high"
    # Rule 3: C-pep < 0.5
    if cpep is not None and cpep < 0.5:
        return "중위험", "aggregate_floor:rule3_cpep_low"
    # Rule 4: 유병 ≥ 10년 + HbA1c ≥ 8.5
    if dm_dur is not None and dm_dur >= 10 and hba1c is not None and hba1c >= 8.5:
        return "중위험", "aggregate_floor:rule4_long_duration_high_a1c"
    return None, None


def highest_level(levels) -> str | None:
    valid = [lv for lv in levels if lv in LEVEL_RANK]
    if not valid:
        return None
    return max(valid, key=lambda lv: LEVEL_RANK[lv])


def flag_summary(*items) -> str:
    flags = []
    for item in items:
        for flag in item.get("clinical_flags") or []:
            if isinstance(flag, dict):
                flags.append(f"{flag.get('type')}:{flag.get('severity')}")
    return "; ".join(sorted(set(flags)))


def main():
    df = load_19()
    print(f"=== v2.1.5 안전망 4룰 + C-pep 6단계 회귀 검증 — 19명 전체 ===\n")

    rows = []
    failed_assertions = []
    for _, row in df.iterrows():
        pdict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        try:
            pred = predict_all(pdict)
        except Exception as e:
            print(f"  ❌ {row['chart_no']} {row['name']}: predict_all 예외 — {type(e).__name__}: {e}")
            failed_assertions.append(f"{row['chart_no']}: predict_all 예외")
            continue

        r = pred.get("retinopathy", {})
        k = pred.get("kidney_disease", {})
        c = pred.get("cardiovascular", {})

        levels_avail = [d.get("level") for d in (r, k, c) if d.get("available")]
        ml_overall = highest_level(levels_avail)
        aggregate_floor, aggregate_floor_reason = aggregate_clinical_floor(row)
        overall = highest_level([ml_overall, aggregate_floor]) or "분석실패"

        # 개별 합병증 floor 사유 수집. C-pep 는 clinical_flags 로만 수집한다.
        all_floor_reasons = set()
        for d in (r, k, c):
            for f in d.get("clinical_floor_reasons") or []:
                all_floor_reasons.add(f)
        if aggregate_floor_reason:
            all_floor_reasons.add(aggregate_floor_reason)

        for label, d in (("retinopathy", r), ("kidney", k), ("cardio", c)):
            if d.get("available") and d.get("score") != d.get("raw_score"):
                failed_assertions.append(
                    f"{row['chart_no']} {label}: score {d.get('score')} != raw_score {d.get('raw_score')}"
                )

        rows.append({
            "chart_no": row["chart_no"],
            "name": row["name"],
            "sex": row["sex"],
            "hba1c": row.get("hba1c"),
            "c_peptide": row.get("c_peptide"),
            "fbg": row.get("fbg"),
            "dm_duration": row.get("DM_diagnosis_age", None) and (None if pd.isna(row.get("DM_diagnosis_age")) else None),
            # 망막
            "retinopathy_raw_score": r.get("raw_score"),
            "retinopathy_score": r.get("score"),
            "retinopathy_level": r.get("level"),
            "retinopathy_threshold": r.get("model_threshold"),
            "retinopathy_cpep_adj": r.get("cpep_adjustment"),
            # 신장
            "kidney_raw_score": k.get("raw_score"),
            "kidney_score": k.get("score"),
            "kidney_level": k.get("level"),
            "kidney_threshold": k.get("model_threshold"),
            "kidney_cpep_adj": k.get("cpep_adjustment"),
            # 심혈관
            "cardio_raw_score": c.get("raw_score"),
            "cardio_score": c.get("score"),
            "cardio_level": c.get("level"),
            "cardio_threshold": c.get("model_threshold"),
            # 종합
            "overall_level": overall,
            "ml_overall_level": ml_overall,
            "aggregate_floor": aggregate_floor_reason or "",
            "clinical_floor_reasons": "; ".join(sorted(all_floor_reasons)),
            "clinical_flags": flag_summary(r, k, c),
            "risk_sources_retina": ",".join(r.get("risk_sources") or []),
            "risk_sources_kidney": ",".join(k.get("risk_sources") or []),
            "risk_sources_cardio": ",".join(c.get("risk_sources") or []),
        })

        # 의료진 지적 케이스 assertion
        cn = row["chart_no"]
        if cn in EXPECTED_HIGH:
            exp_name, exp_level, exp_reason = EXPECTED_HIGH[cn]
            if overall == exp_level:
                print(f"  ✅ {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall} ({exp_reason})")
            else:
                print(f"  ❌ {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall} (기대: {exp_level} — {exp_reason})")
                failed_assertions.append(f"{cn}: 기대 {exp_level}, 실제 {overall}")
        elif cn in EXPECTED_MID:
            exp_name, exp_level, exp_reason = EXPECTED_MID[cn]
            if overall == exp_level:
                print(f"  ✅ {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall} ({exp_reason})")
            else:
                print(f"  ❌ {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall} (기대: {exp_level} — {exp_reason})")
                failed_assertions.append(f"{cn}: 기대 {exp_level}, 실제 {overall}")
        elif cn in EXPECTED_LOW:
            exp_level = "저위험"
            if overall == exp_level:
                print(f"  ✅ {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall} (저위험 유지)")
            else:
                print(f"  ❌ {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall} (기대: 저위험)")
                failed_assertions.append(f"{cn}: 기대 저위험, 실제 {overall}")
        else:
            print(f"     {cn} {row['name']:<6} HbA1c={row['hba1c']:>4.1f} C-펩={row['c_peptide']:>4.2f} → {overall}  (망막:{r.get('level')} 신장:{k.get('level')} 심혈관:{c.get('level')})")

    # CSV 저장
    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n=== 결과 CSV: {OUT_CSV} ===")

    # 종합 분포
    print(f"\n=== 등급 분포 (19명) ===")
    distribution = out_df["overall_level"].value_counts()
    print(distribution)

    # 안전망 적용 카운트
    floor_count = out_df["clinical_floor_reasons"].apply(lambda s: bool(s)).sum()
    flag_count = out_df["clinical_flags"].apply(lambda s: bool(s)).sum()
    low_count = int(distribution.get("저위험", 0))
    print(f"\n종합 안전망 적용된 환자: {floor_count} / {len(out_df)}")
    print(f"clinical_flags 표시 환자: {flag_count} / {len(out_df)}")
    print(f"저위험 환자 수: {low_count} / {len(out_df)}")

    if low_count < MIN_LOW_COUNT:
        failed_assertions.append(f"저위험 {low_count}명: 기대 최소 {MIN_LOW_COUNT}명")

    if failed_assertions:
        print(f"\n❌ 회귀 실패 {len(failed_assertions)}건:")
        for msg in failed_assertions:
            print(f"  - {msg}")
        sys.exit(1)
    else:
        print(f"\n✅ 회귀 통과 — 고위험 {len(EXPECTED_HIGH)}건 + 중위험 {len(EXPECTED_MID)}건 + 저위험 유지 {len(EXPECTED_LOW)}건")
        sys.exit(0)


if __name__ == "__main__":
    main()
