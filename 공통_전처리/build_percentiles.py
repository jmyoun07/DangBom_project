"""
KNHANES 학습 cohort 의 ML 점수 분포 → 연령대별 percentile boundary JSON 생성.

목적:
  병원 환자에게 "동일 연령대 KNHANES 코호트 대비 위험도가 상위 X%" 안내.
  Dashboard / PatientDetail 의 위험도 배지 옆에 노출하여 임상적 맥락 부여.

산출물:
  backend/ml/models/knhanes_percentiles.json
  {
    "kidney_disease": {
      "30-39": {"p10": 5.2, "p20": 8.1, ..., "p90": 78.5, "n": 1234},
      "40-49": {...},
      ...
    },
    "retinopathy": {...},
    "cardiovascular": {...}
  }

실행:
    python 공통_전처리/build_percentiles.py
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

CSV_PATHS = {
    "retinopathy":    ROOT / "망막병증"  / "development.csv",
    "kidney_disease": ROOT / "신장질환"  / "development.csv",
    "cardiovascular": ROOT / "심혈관"    / "development.csv",
}
PKL_PATHS = {
    "retinopathy":    ROOT / "backend" / "ml" / "models" / "retinopathy_model.pkl",
    "kidney_disease": ROOT / "backend" / "ml" / "models" / "dkd_model.pkl",
    "cardiovascular": ROOT / "backend" / "ml" / "models" / "cvd_model.pkl",
}
OUT_PATH = ROOT / "backend" / "ml" / "models" / "knhanes_percentiles.json"

# 연령대 구간 — 10세 단위 (KNHANES 대상 19~80+ 세 커버)
AGE_BUCKETS = [
    ("19-29", 19, 30),
    ("30-39", 30, 40),
    ("40-49", 40, 50),
    ("50-59", 50, 60),
    ("60-69", 60, 70),
    ("70-79", 70, 80),
    ("80+",   80, 200),
]
PERCENTILES = list(range(10, 100, 10))  # 10, 20, ..., 90


def load_model(name: str) -> dict:
    with open(PKL_PATHS[name], "rb") as f:
        pkg = pickle.load(f)
    # n_jobs=1 강제 (병렬 워커 spawn 방지)
    def walk(o, seen=set()):
        if o is None or id(o) in seen:
            return
        seen.add(id(o))
        if hasattr(o, "n_jobs"):
            try:
                o.n_jobs = 1
            except Exception:
                pass
        d = getattr(o, "__dict__", None)
        if isinstance(d, dict):
            for v in list(d.values()):
                walk(v, seen)
        if isinstance(o, (list, tuple, set, frozenset)):
            for x in o:
                walk(x, seen)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v, seen)
    walk(pkg)
    return pkg


def predict_scores(pkg: dict, df: pd.DataFrame) -> np.ndarray:
    """학습된 pkg 의 features 기준으로 dataframe 점수 (0~100) 산출."""
    feats = pkg["features"]
    X = df.copy()
    for c in feats:
        if c not in X.columns:
            X[c] = np.nan
    X = X[feats]
    if pkg.get("imputer") is not None:
        X = pd.DataFrame(pkg["imputer"].transform(X), columns=feats)
    if pkg.get("scaler") is not None:
        X = pd.DataFrame(pkg["scaler"].transform(X), columns=feats)

    model_type = pkg.get("model_type", "")
    if model_type == "Stacking" and "stacking" in pkg:
        st = pkg["stacking"]
        base_order = st.get("base_order", ["xgb", "lgb", "cb"])
        base_probs = []
        for k in base_order:
            base_probs.append(st["base_models"][k].predict_proba(X)[:, 1])
        meta_in = np.stack(base_probs, axis=1)
        probs = st["meta_model"].predict_proba(meta_in)[:, 1]
    else:
        probs = pkg["model"].predict_proba(X)[:, 1]
    return probs * 100.0


def compute_bucket_stats(scores: np.ndarray, ages: np.ndarray) -> dict:
    """연령대별 percentile boundary 계산."""
    out = {}
    for label, lo, hi in AGE_BUCKETS:
        mask = (ages >= lo) & (ages < hi)
        sub = scores[mask]
        if len(sub) < 30:  # 표본 부족 — 통계적 의미 X
            continue
        stats = {f"p{p}": round(float(np.percentile(sub, p)), 2) for p in PERCENTILES}
        stats["n"] = int(len(sub))
        stats["mean"] = round(float(np.mean(sub)), 2)
        stats["median"] = round(float(np.median(sub)), 2)
        out[label] = stats
    return out


def main():
    out = {"meta": {"buckets": [b[0] for b in AGE_BUCKETS], "percentiles": PERCENTILES}}
    for disease in ["retinopathy", "kidney_disease", "cardiovascular"]:
        csv_path = CSV_PATHS[disease]
        if not csv_path.exists():
            print(f"  [skip] {disease}: CSV 없음 ({csv_path})")
            continue
        print(f"\n[{disease}] CSV 로드 중...")
        df = pd.read_csv(csv_path)
        if "age" not in df.columns:
            print(f"  [warn] age 컬럼 없음")
            continue
        print(f"  데이터 {len(df):,} 명")

        pkg = load_model(disease)
        print(f"  pkg loaded ({pkg.get('model_type', '?')})")

        scores = predict_scores(pkg, df)
        ages = df["age"].astype(float).values
        print(f"  점수 분포 mean={scores.mean():.1f} median={np.median(scores):.1f}")

        out[disease] = compute_bucket_stats(scores, ages)
        for label, stats in out[disease].items():
            print(f"    {label}: n={stats['n']:>5}  median={stats['median']:>5.1f}  p90={stats['p90']:>5.1f}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {OUT_PATH}")


if __name__ == "__main__":
    main()
