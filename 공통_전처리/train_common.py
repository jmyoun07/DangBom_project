"""
공통 학습 모듈 — 3개 질환 모델에 공유되는 파이프라인.

- 입력: development.csv, validation.csv (target 컬럼 포함)
- 출력: model.pkl, training_summary.json, feature_importance.png

pkl 구조:
{
    'model':        sklearn/xgboost classifier,
    'model_type':   'XGBoost' | 'EasyEnsemble' | ...,
    'imputer':      KNNImputer,
    'scaler':       StandardScaler,
    'features':     List[str],  # 학습 순서대로 42개
    'feature_groups': Dict[str, List[str]],
    'threshold':    float,      # Youden's J 최적 임계값
    'performance':  {...},
    'version':      'v2.0-unified',
}
"""
import os
import json
import pickle
import warnings
from typing import Callable

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from sklearn.impute import KNNImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score, accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix, roc_curve,
)

warnings.filterwarnings("ignore")

# 한글 폰트 (Windows 환경 기본)
for font in ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]:
    try:
        rcParams["font.family"] = font
        break
    except Exception:
        continue
rcParams["axes.unicode_minus"] = False

META_COLS = {"survey_year", "target"}


def load_split(dev_csv: str, val_csv: str):
    dev = pd.read_csv(dev_csv)
    val = pd.read_csv(val_csv)
    feature_cols = [c for c in dev.columns if c not in META_COLS]
    return dev, val, feature_cols


def fit_preprocessors(X_train: pd.DataFrame):
    imputer = KNNImputer(n_neighbors=5)
    scaler = StandardScaler()
    X_imp = imputer.fit_transform(X_train)
    X_scl = scaler.fit_transform(X_imp)
    return imputer, scaler, X_scl


def apply_preprocessors(imputer, scaler, X: pd.DataFrame):
    return scaler.transform(imputer.transform(X))


def evaluate(y_true, y_proba, threshold: float = None):
    fpr, tpr, thr = roc_curve(y_true, y_proba)
    j = tpr - fpr
    if threshold is None:
        threshold = float(thr[np.argmax(j)])
    y_pred = (y_proba >= threshold).astype(int)

    auc = roc_auc_score(y_true, y_proba)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    sens = tp / (tp + fn) if (tp + fn) else 0
    spec = tn / (tn + fp) if (tn + fp) else 0
    prec = precision_score(y_true, y_pred, zero_division=0)
    f1   = f1_score(y_true, y_pred)
    acc  = accuracy_score(y_true, y_pred)
    npv  = tn / (tn + fn) if (tn + fn) else 0

    return {
        "threshold":   float(threshold),
        "auc":         float(auc),
        "sensitivity": float(sens),
        "specificity": float(spec),
        "precision":   float(prec),
        "f1":          float(f1),
        "accuracy":    float(acc),
        "npv":         float(npv),
        "tp": int(tp), "tn": int(tn), "fp": int(fp), "fn": int(fn),
    }


def _extract_importance_recursive(est):
    """nested estimator (EasyEnsemble → BalancedBagging → Pipeline → AdaBoost) 에서 재귀 추출."""
    if hasattr(est, "feature_importances_"):
        try:
            return np.asarray(est.feature_importances_, dtype=float)
        except Exception:
            pass
    # sklearn Pipeline
    if hasattr(est, "steps"):
        return _extract_importance_recursive(est.steps[-1][1])
    # AdaBoost / Bagging: sub-estimators
    if hasattr(est, "estimators_"):
        subs = [_extract_importance_recursive(e) for e in est.estimators_]
        subs = [s for s in subs if s is not None]
        if subs:
            return np.mean(np.stack(subs, axis=0), axis=0)
    # Logistic coefs
    if hasattr(est, "coef_"):
        try:
            return np.abs(est.coef_).ravel()
        except Exception:
            pass
    return None


def save_feature_importance(model, feature_names, out_path: str, top_n: int = 25):
    imp = _extract_importance_recursive(model)

    if imp is None:
        print("  [warn] feature importance 추출 불가 (모델에 지원 속성 없음)")
        return None

    fi = pd.Series(imp, index=feature_names).sort_values(ascending=True).tail(top_n)

    fig, ax = plt.subplots(figsize=(9, 0.35 * len(fi) + 1.5))
    ax.barh(fi.index, fi.values, color="#6366f1")
    ax.set_xlabel("Importance")
    ax.set_title(f"Top {top_n} Feature Importance")
    plt.tight_layout()
    plt.savefig(out_path, dpi=110)
    plt.close()
    return fi.sort_values(ascending=False).to_dict()


def save_artifacts(
    out_dir: str,
    model, model_type: str,
    imputer, scaler,
    features, feature_groups,
    threshold: float,
    dev_metrics: dict, val_metrics: dict,
    trials: dict,
    extra: dict = None,
):
    pkl_path = os.path.join(out_dir, "model.pkl")
    pkg = {
        "model":         model,
        "model_type":    model_type,
        "imputer":       imputer,
        "scaler":        scaler,
        "features":      list(features),
        "feature_groups": feature_groups,
        "threshold":     float(threshold),
        "performance":   val_metrics,
        "version":       "v2.0-unified",
    }
    with open(pkl_path, "wb") as f:
        pickle.dump(pkg, f)

    summary = {
        "model_type":     model_type,
        "version":        "v2.0-unified",
        "n_features":     len(features),
        "features":       list(features),
        "feature_groups": feature_groups,
        "threshold":      float(threshold),
        "dev_metrics":    dev_metrics,
        "val_metrics":    val_metrics,
        "trials":         trials,
    }
    if extra:
        summary.update(extra)
    with open(os.path.join(out_dir, "training_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return pkl_path
