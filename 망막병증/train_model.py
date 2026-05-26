"""
망막병증 (DR) 예측 모델 — XGBoost 재학습
통일 42개 독립변수 사용.
"""
import os
import sys
import io
import json
import numpy as np
import pandas as pd

import xgboost as xgb
from imblearn.over_sampling import BorderlineSMOTE, SMOTE

# 공통 모듈 import
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
print("망막병증 (DR) 모델 학습 v2.0 — 통일 42변수")
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

# 전처리
imputer, scaler, X_dev = fit_preprocessors(X_dev_raw)
X_val = apply_preprocessors(imputer, scaler, X_val_raw)

# SMOTE (BorderlineSMOTE 우선, 실패 시 SMOTE)
k_neighbors = min(5, int(y_dev.sum()) - 1)
try:
    sm = BorderlineSMOTE(random_state=42, k_neighbors=k_neighbors)
    X_dev_res, y_dev_res = sm.fit_resample(X_dev, y_dev)
    sm_type = "BorderlineSMOTE"
except Exception as e:
    sm = SMOTE(random_state=42, k_neighbors=max(1, k_neighbors - 2))
    X_dev_res, y_dev_res = sm.fit_resample(X_dev, y_dev)
    sm_type = "SMOTE(fallback)"
print(f"  oversampling: {sm_type}, 학습 샘플 {len(X_dev_res)}")

# XGBoost 학습
params = dict(
    n_estimators=300, max_depth=4, learning_rate=0.03,
    subsample=0.8, colsample_bytree=0.8,
    min_child_weight=3, gamma=0.1,
    reg_alpha=0.5, reg_lambda=1.0,
    random_state=42, eval_metric="logloss",
)
model = xgb.XGBClassifier(**params)
model.fit(X_dev_res, y_dev_res)

# 평가 — dev 에서 Youden's J 로 threshold 결정
dev_proba = model.predict_proba(X_dev)[:, 1]
dev_metrics = evaluate(y_dev, dev_proba)  # 임계값 자동 선택
threshold = dev_metrics["threshold"]
val_proba = model.predict_proba(X_val)[:, 1]
val_metrics = evaluate(y_val, val_proba, threshold=threshold)

print(f"\n[학습 결과]")
print(f"  dev  : AUC={dev_metrics['auc']:.4f}, 임계값={threshold:.4f}, 민감도={dev_metrics['sensitivity']:.3f}, 특이도={dev_metrics['specificity']:.3f}")
print(f"  val  : AUC={val_metrics['auc']:.4f}, 민감도={val_metrics['sensitivity']:.3f}, 특이도={val_metrics['specificity']:.3f}, F1={val_metrics['f1']:.3f}")

# 변수 중요도 그래프
fi_dict = save_feature_importance(model, feature_cols, os.path.join(OUT_DIR, "feature_importance.png"))

# dataset_meta.json 에서 feature_groups 가져오기
with open(META_JSON, encoding="utf-8") as f:
    dataset_meta = json.load(f)

pkl_path = save_artifacts(
    out_dir=OUT_DIR,
    model=model, model_type="XGBoost",
    imputer=imputer, scaler=scaler,
    features=feature_cols,
    feature_groups=dataset_meta.get("feature_groups", {}),
    threshold=threshold,
    dev_metrics=dev_metrics, val_metrics=val_metrics,
    trials={
        "algorithm":     "XGBoost",
        "hyperparameters": params,
        "oversampling":  sm_type,
        "n_samples_after_smote": int(len(X_dev_res)),
        "threshold_method": "Youden's J on development",
    },
    extra={"feature_importance": fi_dict},
)
print(f"\n  → 저장: {pkl_path}")
print("=" * 70)
