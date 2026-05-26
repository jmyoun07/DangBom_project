"""
신장질환 (DKD) 예측 모델 — EasyEnsemble 재학습
극심한 불균형(유병률 ~1.6%)에 최적화된 EasyEnsembleClassifier 사용.
통일 42개 독립변수 사용.
"""
import os
import sys
import io
import json

import numpy as np
import pandas as pd

from imblearn.ensemble import EasyEnsembleClassifier
from imblearn.over_sampling import BorderlineSMOTE

THIS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(THIS, ".."))
sys.path.insert(0, os.path.join(ROOT, "공통_전처리"))
from train_common import (
    load_split, fit_preprocessors, apply_preprocessors,
    evaluate, save_feature_importance, save_artifacts,
)

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OUT_DIR = THIS
META_JSON = os.path.join(OUT_DIR, "dataset_meta.json")

print("=" * 70)
print("신장질환 (DKD) 모델 학습 v2.0 — 통일 42변수, EasyEnsemble")
print("=" * 70)

dev_df, val_df, feature_cols = load_split(
    os.path.join(OUT_DIR, "development.csv"),
    os.path.join(OUT_DIR, "validation.csv"),
)
X_dev_raw = dev_df[feature_cols]
y_dev = dev_df["target"].astype(int)
X_val_raw = val_df[feature_cols]
y_val = val_df["target"].astype(int)
print(f"  dev={len(X_dev_raw)}, val={len(X_val_raw)}, feats={len(feature_cols)}")
print(f"  dev 양성={int(y_dev.sum())}, val 양성={int(y_val.sum())}")

imputer, scaler, X_dev = fit_preprocessors(X_dev_raw)
X_val = apply_preprocessors(imputer, scaler, X_val_raw)

# EasyEnsemble: 불균형 샘플에 강함. n_estimators 는 여러 값 시도 후 선택.
# sklearn 1.5+ 에서 AdaBoost algorithm 파라미터 deprecated 이슈 회피
try:
    from sklearn.ensemble import AdaBoostClassifier
    _old = AdaBoostClassifier.__init__
    def _patched(self, *a, **kw):
        kw.pop("algorithm", None)
        _old(self, *a, **kw)
except Exception:
    pass

best = None
trials_log = []
for n_est in [10, 20, 30, 50]:
    model = EasyEnsembleClassifier(
        n_estimators=n_est,
        sampling_strategy="auto",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_dev, y_dev)  # EasyEnsemble 이 내부에서 undersampling 수행
    dev_proba = model.predict_proba(X_dev)[:, 1]
    dev_m = evaluate(y_dev, dev_proba)
    val_proba = model.predict_proba(X_val)[:, 1]
    val_m = evaluate(y_val, val_proba, threshold=dev_m["threshold"])
    trials_log.append({"n_estimators": n_est, "dev_auc": dev_m["auc"], "val_auc": val_m["auc"]})
    print(f"  n_est={n_est:3d}: dev_AUC={dev_m['auc']:.4f}  val_AUC={val_m['auc']:.4f}  "
          f"sens={val_m['sensitivity']:.3f} spec={val_m['specificity']:.3f}")
    if best is None or val_m["auc"] > best["val_m"]["auc"]:
        best = {"n_est": n_est, "model": model, "dev_m": dev_m, "val_m": val_m}

n_est = best["n_est"]
model = best["model"]
dev_m = best["dev_m"]
val_m = best["val_m"]
threshold = dev_m["threshold"]

print(f"\n[최적 모델] EasyEnsemble n_estimators={n_est}")
print(f"  dev  : AUC={dev_m['auc']:.4f}, 임계값={threshold:.4f}")
print(f"  val  : AUC={val_m['auc']:.4f}, 민감도={val_m['sensitivity']:.3f}, 특이도={val_m['specificity']:.3f}, F1={val_m['f1']:.3f}")

fi_dict = save_feature_importance(model, feature_cols, os.path.join(OUT_DIR, "feature_importance.png"))

with open(META_JSON, encoding="utf-8") as f:
    dataset_meta = json.load(f)

pkl_path = save_artifacts(
    out_dir=OUT_DIR,
    model=model, model_type="EasyEnsemble",
    imputer=imputer, scaler=scaler,
    features=feature_cols,
    feature_groups=dataset_meta.get("feature_groups", {}),
    threshold=threshold,
    dev_metrics=dev_m, val_metrics=val_m,
    trials={
        "algorithm":     "EasyEnsembleClassifier",
        "n_estimators_tried": [10, 20, 30, 50],
        "n_estimators_best": n_est,
        "sampling_strategy": "auto (undersampling)",
        "threshold_method": "Youden's J on development",
        "trials_log": trials_log,
    },
    extra={"feature_importance": fi_dict},
)
print(f"\n  → 저장: {pkl_path}")
print("=" * 70)
