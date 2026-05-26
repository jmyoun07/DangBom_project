"""
재학습 (debias) 공통 모듈 — DKD / CVD 두 모델에 공유.

목표:
1) AUC 향상 — Optuna 150 trials × 다중 알고리즘 + stacking
2) 데이터 불균형 — scale_pos_weight, SMOTE, EasyEnsemble 비교
3) Threshold — Youden's J + cost-weighted F1.5 (민감도 가중) 비교
4) 역인과 완화 — insulin_medication / DM_medication 에:
   - monotonic constraint = +1 (자연적 방향 강제)
   - feature weight = 0.5 (tree split 빈도 감소)
   - sample weight cap (insulin=1 OR dm_med=1 → 0.7 가중치)

사용:
    from train_debias_common import run_debias_training
    run_debias_training(disease="DKD", out_dir="신장질환", n_trials=150)
"""
from __future__ import annotations

import os
import io
import sys
import json
import time
import pickle
import warnings
from typing import Callable

import numpy as np
import pandas as pd

import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner

import xgboost as xgb
import lightgbm as lgb
import catboost as cb

from sklearn.model_selection import StratifiedKFold
from sklearn.impute import KNNImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, accuracy_score, precision_score, recall_score,
    f1_score, confusion_matrix, roc_curve, fbeta_score,
)
from sklearn.calibration import CalibratedClassifierCV

from imblearn.ensemble import EasyEnsembleClassifier

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.INFO)  # 진행률 표시

# UTF-8 stdout (Windows console) — line-buffered so file redirects flush per line
if hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                       line_buffering=True, write_through=True)
    except Exception:
        pass
if hasattr(sys.stderr, "buffer"):
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                       line_buffering=True, write_through=True)
    except Exception:
        pass

# ── 역인과 대상 변수 ────────────────────────────────────────────
DEBIAS_FEATURES = ["insulin_medication", "DM_medication"]

META_COLS = {"survey_year", "target"}
RANDOM_STATE = 42
N_FOLDS = 5


# ── 데이터 로드 + 전처리 ────────────────────────────────────────

def load_split(out_dir: str):
    dev = pd.read_csv(os.path.join(out_dir, "development.csv"))
    val = pd.read_csv(os.path.join(out_dir, "validation.csv"))
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


# ── 평가 ────────────────────────────────────────────────────────

def evaluate(y_true, y_proba, threshold: float | None = None,
             threshold_method: str = "youden"):
    """threshold_method: 'youden' | 'fbeta1.5' (민감도 가중)"""
    fpr, tpr, thr_arr = roc_curve(y_true, y_proba)
    if threshold is None:
        if threshold_method == "fbeta1.5":
            best_t, best_score = 0.5, -1.0
            for t in np.linspace(0.01, 0.99, 99):
                pred = (y_proba >= t).astype(int)
                if pred.sum() == 0:
                    continue
                s = fbeta_score(y_true, pred, beta=1.5, zero_division=0)
                if s > best_score:
                    best_score, best_t = s, float(t)
            threshold = best_t
        else:
            j = tpr - fpr
            threshold = float(thr_arr[np.argmax(j)])

    y_pred = (y_proba >= threshold).astype(int)
    auc = roc_auc_score(y_true, y_proba)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    sens = tp / (tp + fn) if (tp + fn) else 0
    spec = tn / (tn + fp) if (tn + fp) else 0
    prec = precision_score(y_true, y_pred, zero_division=0)
    f1   = f1_score(y_true, y_pred, zero_division=0)
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


# ── 역인과 완화 ─────────────────────────────────────────────────

def make_sample_weights(X_raw: pd.DataFrame, debias_cap: float = 0.7) -> np.ndarray:
    """insulin_medication=1 OR DM_medication=1 인 샘플의 가중치를 cap 만큼 감소."""
    w = np.ones(len(X_raw), dtype=float)
    mask = np.zeros(len(X_raw), dtype=bool)
    for f in DEBIAS_FEATURES:
        if f in X_raw.columns:
            mask |= (X_raw[f].fillna(0) >= 1).to_numpy()
    w[mask] = debias_cap
    return w


def get_monotone_constraints(feature_cols: list[str]) -> str:
    """XGBoost monotone_constraints 형식 — 역인과 변수에 +1 강제."""
    arr = []
    for f in feature_cols:
        if f in DEBIAS_FEATURES:
            arr.append(1)
        else:
            arr.append(0)
    return "(" + ",".join(str(a) for a in arr) + ")"


def get_lgb_monotone(feature_cols: list[str]) -> list[int]:
    return [1 if f in DEBIAS_FEATURES else 0 for f in feature_cols]


def get_feature_weights(feature_cols: list[str], discount: float = 0.5) -> np.ndarray:
    """역인과 변수의 split 빈도를 줄이는 가중치 (XGB feature_weights)."""
    return np.array([discount if f in DEBIAS_FEATURES else 1.0 for f in feature_cols], dtype=float)


# ── Optuna objective: 모델별 ───────────────────────────────────

def objective_xgb(trial, X, y, w, feat_cols, scale_pos_weight: float):
    params = {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "tree_method": "hist",
        "verbosity": 0,
        "n_estimators":      trial.suggest_int("n_estimators", 200, 800),
        "max_depth":         trial.suggest_int("max_depth", 3, 9),
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "min_child_weight":  trial.suggest_float("min_child_weight", 0.5, 10.0),
        "gamma":             trial.suggest_float("gamma", 0.0, 5.0),
        "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
        "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        "scale_pos_weight":  scale_pos_weight,
        "monotone_constraints": get_monotone_constraints(feat_cols),
        "random_state": RANDOM_STATE,
        "early_stopping_rounds": 30,
    }
    feat_w = get_feature_weights(feat_cols, 0.5)
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(y))
    for fold, (tr, te) in enumerate(skf.split(X, y)):
        model = xgb.XGBClassifier(**params)
        model.fit(
            X[tr], y[tr],
            sample_weight=w[tr],
            feature_weights=feat_w,
            eval_set=[(X[te], y[te])],
            verbose=False,
        )
        oof[te] = model.predict_proba(X[te])[:, 1]
        # report intermediate
        trial.report(roc_auc_score(y[te], oof[te]), fold)
        if trial.should_prune():
            raise optuna.TrialPruned()
    return roc_auc_score(y, oof)


def objective_lgb(trial, X, y, w, feat_cols, scale_pos_weight: float):
    params = {
        "objective": "binary",
        "metric": "auc",
        "verbosity": -1,
        "boosting_type": "gbdt",
        "n_estimators":     trial.suggest_int("n_estimators", 200, 800),
        "num_leaves":       trial.suggest_int("num_leaves", 15, 127),
        "max_depth":        trial.suggest_int("max_depth", 3, 9),
        "learning_rate":    trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "bagging_freq":     trial.suggest_int("bagging_freq", 1, 7),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 60),
        "reg_alpha":        trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
        "reg_lambda":       trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        "scale_pos_weight": scale_pos_weight,
        "monotone_constraints": get_lgb_monotone(feat_cols),
        "random_state": RANDOM_STATE,
        "n_jobs": -1,
    }
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(y))
    for fold, (tr, te) in enumerate(skf.split(X, y)):
        model = lgb.LGBMClassifier(**params)
        model.fit(X[tr], y[tr], sample_weight=w[tr],
                  eval_set=[(X[te], y[te])],
                  callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)])
        oof[te] = model.predict_proba(X[te])[:, 1]
        trial.report(roc_auc_score(y[te], oof[te]), fold)
        if trial.should_prune():
            raise optuna.TrialPruned()
    return roc_auc_score(y, oof)


def objective_cb(trial, X, y, w, feat_cols, prevalence: float):
    params = {
        "iterations":    trial.suggest_int("iterations", 200, 800),
        "depth":         trial.suggest_int("depth", 4, 9),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "l2_leaf_reg":   trial.suggest_float("l2_leaf_reg", 1.0, 30.0),
        "border_count":  trial.suggest_int("border_count", 32, 254),
        "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 5.0),
        "auto_class_weights": "Balanced",
        "loss_function": "Logloss",
        "eval_metric":   "AUC",
        "random_seed":   RANDOM_STATE,
        "verbose":       False,
        "thread_count":  -1,
        "od_type":       "Iter",
        "od_wait":       30,
    }
    # CatBoost monotonic 은 feature 인덱스 dict 형식
    mono = {i: 1 for i, f in enumerate(feat_cols) if f in DEBIAS_FEATURES}
    if mono:
        params["monotone_constraints"] = mono

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(y))
    for fold, (tr, te) in enumerate(skf.split(X, y)):
        model = cb.CatBoostClassifier(**params)
        model.fit(X[tr], y[tr], sample_weight=w[tr],
                  eval_set=(X[te], y[te]), verbose=False)
        oof[te] = model.predict_proba(X[te])[:, 1]
        trial.report(roc_auc_score(y[te], oof[te]), fold)
        if trial.should_prune():
            raise optuna.TrialPruned()
    return roc_auc_score(y, oof)


# ── 베스트 파라미터 → 풀-데이터 학습 ────────────────────────────

def fit_best_xgb(best_params, X, y, w, feat_cols, scale_pos_weight):
    params = dict(best_params)
    # 풀-fit 시에는 early_stopping_rounds 제거 (eval_set 없음)
    params.pop("early_stopping_rounds", None)
    params.update({
        "objective": "binary:logistic", "eval_metric": "auc",
        "tree_method": "hist", "verbosity": 0,
        "scale_pos_weight": scale_pos_weight,
        "monotone_constraints": get_monotone_constraints(feat_cols),
        "random_state": RANDOM_STATE,
    })
    feat_w = get_feature_weights(feat_cols, 0.5)
    m = xgb.XGBClassifier(**params)
    m.fit(X, y, sample_weight=w, feature_weights=feat_w, verbose=False)
    return m


def fit_best_lgb(best_params, X, y, w, feat_cols, scale_pos_weight):
    params = dict(best_params)
    params.update({
        "objective": "binary", "metric": "auc", "verbosity": -1,
        "boosting_type": "gbdt",
        "scale_pos_weight": scale_pos_weight,
        "monotone_constraints": get_lgb_monotone(feat_cols),
        "random_state": RANDOM_STATE, "n_jobs": -1,
    })
    m = lgb.LGBMClassifier(**params)
    m.fit(X, y, sample_weight=w)
    return m


def fit_best_cb(best_params, X, y, w, feat_cols):
    params = dict(best_params)
    # od_* 는 eval_set 없으면 의미 없음 — 제거
    params.pop("od_type", None)
    params.pop("od_wait", None)
    params.update({
        "auto_class_weights": "Balanced", "loss_function": "Logloss",
        "eval_metric": "AUC", "random_seed": RANDOM_STATE,
        "verbose": False, "thread_count": -1,
    })
    mono = {i: 1 for i, f in enumerate(feat_cols) if f in DEBIAS_FEATURES}
    if mono:
        params["monotone_constraints"] = mono
    m = cb.CatBoostClassifier(**params)
    m.fit(X, y, sample_weight=w, verbose=False)
    return m


# ── OOF 생성 (스태킹 메타-학습 데이터용) ────────────────────────

def make_oof_predictions(model_factory: Callable, X, y, w):
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(y))
    for tr, te in skf.split(X, y):
        m = model_factory()
        # 학습은 제공된 sample_weight 적용
        try:
            m.fit(X[tr], y[tr], sample_weight=w[tr])
        except TypeError:
            m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    return oof


# ── EasyEnsemble (불균형 비교용) ────────────────────────────────

def fit_easy_ensemble(X, y, n_estimators_list=(20, 50, 80)):
    """sklearn 1.5.2: AdaBoost.algorithm 가 'deprecated' default 지만 아직 사용 가능 → 패치 불필요."""
    from sklearn.ensemble import AdaBoostClassifier
    # 명시적 base estimator (sklearn 1.5.2 호환)
    def _make_ee(n):
        # algorithm='SAMME' 명시 (sklearn 1.5+ 'SAMME.R' deprecated)
        try:
            base = AdaBoostClassifier(n_estimators=10, algorithm="SAMME",
                                       random_state=RANDOM_STATE)
        except TypeError:
            # sklearn 1.7+ algorithm 제거됨
            base = AdaBoostClassifier(n_estimators=10, random_state=RANDOM_STATE)
        return EasyEnsembleClassifier(
            n_estimators=n,
            estimator=base,
            random_state=RANDOM_STATE, n_jobs=-1,
        )

    best = None
    for n in n_estimators_list:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
        oof = np.zeros(len(y))
        for tr, te in skf.split(X, y):
            m = _make_ee(n)
            m.fit(X[tr], y[tr])
            oof[te] = m.predict_proba(X[te])[:, 1]
        auc = roc_auc_score(y, oof)
        print(f"  EasyEnsemble n={n}: oof AUC={auc:.4f}")
        if best is None or auc > best["oof_auc"]:
            best = {"n_estimators": n, "oof_auc": auc, "oof": oof}

    final = _make_ee(best["n_estimators"])
    final.fit(X, y)
    return final, best


# ── 메인 ────────────────────────────────────────────────────────

def run_debias_training(disease: str, out_dir: str, n_trials: int = 150,
                        debias_cap: float = 0.7):
    """disease: 'DKD' | 'CVD' (출력 라벨 용도)"""
    print("=" * 78)
    print(f"  {disease} debias 재학습 — Optuna {n_trials} trials × 4 algo + stacking")
    print("=" * 78)
    t_start = time.time()

    dev_df, val_df, feat_cols = load_split(out_dir)
    X_dev_raw = dev_df[feat_cols]; y_dev = dev_df["target"].astype(int).to_numpy()
    X_val_raw = val_df[feat_cols]; y_val = val_df["target"].astype(int).to_numpy()
    print(f"  dev={len(X_dev_raw)} (pos={int(y_dev.sum())}, prev={y_dev.mean():.3f})")
    print(f"  val={len(X_val_raw)} (pos={int(y_val.sum())}, prev={y_val.mean():.3f})")

    # 전처리 (KNN imputation + StandardScaler)
    imputer, scaler, X_dev = fit_preprocessors(X_dev_raw)
    X_val = apply_preprocessors(imputer, scaler, X_val_raw)

    # 역인과 sample weight
    w_dev = make_sample_weights(X_dev_raw, debias_cap=debias_cap)
    print(f"  debias 가중치 적용 샘플: {(w_dev < 1).sum()}/{len(w_dev)} ({(w_dev<1).mean():.1%})")

    # scale_pos_weight (음/양 비율)
    n_neg = int((y_dev == 0).sum()); n_pos = int(y_dev.sum())
    spw = n_neg / max(n_pos, 1)
    prevalence = n_pos / len(y_dev)
    print(f"  scale_pos_weight={spw:.2f}, prevalence={prevalence:.3%}\n")

    # ── 1) Optuna × 3 알고리즘 ──────────────────────────────
    studies = {}
    for algo, obj_fn in [
        ("xgb", lambda t: objective_xgb(t, X_dev, y_dev, w_dev, feat_cols, spw)),
        ("lgb", lambda t: objective_lgb(t, X_dev, y_dev, w_dev, feat_cols, spw)),
        ("cb",  lambda t: objective_cb (t, X_dev, y_dev, w_dev, feat_cols, prevalence)),
    ]:
        print(f"  ── Optuna [{algo}] {n_trials} trials ──")
        t0 = time.time()
        study = optuna.create_study(
            direction="maximize",
            sampler=TPESampler(seed=RANDOM_STATE, n_startup_trials=20),
            pruner=MedianPruner(n_startup_trials=10, n_warmup_steps=2),
        )
        study.optimize(obj_fn, n_trials=n_trials, show_progress_bar=False, n_jobs=1)
        elapsed = time.time() - t0
        print(f"    best CV AUC = {study.best_value:.4f}  ({elapsed:.1f}s, "
              f"completed={len([t for t in study.trials if t.state.name=='COMPLETE'])})")
        studies[algo] = study

    # ── 2) 베스트 파라미터로 풀-데이터 재학습 ───────────────
    print("\n  ── 베스트 파라미터로 풀-dev 재학습 ──")
    best_xgb = fit_best_xgb(studies["xgb"].best_params, X_dev, y_dev, w_dev, feat_cols, spw)
    best_lgb = fit_best_lgb(studies["lgb"].best_params, X_dev, y_dev, w_dev, feat_cols, spw)
    best_cb  = fit_best_cb (studies["cb" ].best_params, X_dev, y_dev, w_dev, feat_cols)

    # ── 3) 개별 모델 val 평가 (Youden) ───────────────────────
    individual = {}
    for name, m in [("xgb", best_xgb), ("lgb", best_lgb), ("cb", best_cb)]:
        # CV-OOF 임계값 (overfit 방지)
        oof = np.zeros(len(y_dev))
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
        for tr, te in skf.split(X_dev, y_dev):
            m_cv = type(m)(**m.get_params())
            try:
                m_cv.fit(X_dev[tr], y_dev[tr], sample_weight=w_dev[tr])
            except TypeError:
                m_cv.fit(X_dev[tr], y_dev[tr])
            oof[te] = m_cv.predict_proba(X_dev[te])[:, 1]
        oof_m = evaluate(y_dev, oof, threshold_method="youden")
        val_proba = m.predict_proba(X_val)[:, 1]
        val_m = evaluate(y_val, val_proba, threshold=oof_m["threshold"])
        individual[name] = {"oof_metrics": oof_m, "val_metrics": val_m,
                            "oof_proba": oof, "val_proba": val_proba}
        print(f"    [{name:3s}] oofAUC={oof_m['auc']:.4f}  valAUC={val_m['auc']:.4f}  "
              f"sens={val_m['sensitivity']:.3f} spec={val_m['specificity']:.3f}")

    # ── 4) Stacking (3 base → LR meta) ───────────────────────
    print("\n  ── Stacking ensemble ──")
    oof_matrix = np.column_stack([individual[n]["oof_proba"] for n in ["xgb","lgb","cb"]])
    val_matrix = np.column_stack([individual[n]["val_proba"] for n in ["xgb","lgb","cb"]])
    meta = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced",
                              random_state=RANDOM_STATE)
    meta.fit(oof_matrix, y_dev)
    stack_oof = meta.predict_proba(oof_matrix)[:, 1]
    stack_val = meta.predict_proba(val_matrix)[:, 1]
    stack_oof_m = evaluate(y_dev, stack_oof, threshold_method="youden")
    stack_val_m = evaluate(y_val, stack_val, threshold=stack_oof_m["threshold"])
    print(f"    [stk] oofAUC={stack_oof_m['auc']:.4f}  valAUC={stack_val_m['auc']:.4f}  "
          f"sens={stack_val_m['sensitivity']:.3f} spec={stack_val_m['specificity']:.3f}  "
          f"meta_w={meta.coef_[0]}")

    # ── 5) EasyEnsemble (비교 baseline) ──────────────────────
    print("\n  ── EasyEnsemble (불균형 baseline 비교) ──")
    ee_model = None; ee_best = None; ee_oof_m = None; ee_val_m = None
    try:
        ee_model, ee_best = fit_easy_ensemble(X_dev, y_dev, n_estimators_list=(20, 50, 80))
        ee_oof_m  = evaluate(y_dev, ee_best["oof"], threshold_method="youden")
        ee_val_m  = evaluate(y_val, ee_model.predict_proba(X_val)[:,1], threshold=ee_oof_m["threshold"])
        print(f"    [ee ] oofAUC={ee_oof_m['auc']:.4f}  valAUC={ee_val_m['auc']:.4f}  "
              f"sens={ee_val_m['sensitivity']:.3f} spec={ee_val_m['specificity']:.3f}")
    except Exception as e:
        import traceback
        print(f"    [ee ] 학습 실패 (skip): {e}")
        traceback.print_exc()

    # ── 6) 최종 모델 선정 (OOF AUC 기준) ─────────────────────
    candidates = [
        ("XGBoost",       best_xgb,  individual["xgb"]["oof_metrics"], individual["xgb"]["val_metrics"]),
        ("LightGBM",      best_lgb,  individual["lgb"]["oof_metrics"], individual["lgb"]["val_metrics"]),
        ("CatBoost",      best_cb,   individual["cb" ]["oof_metrics"], individual["cb" ]["val_metrics"]),
        ("Stacking",      ("stack", best_xgb, best_lgb, best_cb, meta), stack_oof_m, stack_val_m),
    ]
    if ee_model is not None and ee_oof_m is not None:
        candidates.append(("EasyEnsemble", ee_model, ee_oof_m, ee_val_m))
    # OOF AUC 로 선정 (val 에 oversfit 방지)
    candidates_sorted = sorted(candidates, key=lambda c: c[2]["auc"], reverse=True)
    best_name, best_model, best_oof, best_val = candidates_sorted[0]
    print(f"\n  >>> 최종 선정: [{best_name}]  oofAUC={best_oof['auc']:.4f}  valAUC={best_val['auc']:.4f}")

    # ── 7) Threshold 비교 (Youden vs F-beta1.5) ─────────────
    if best_name == "Stacking":
        final_val_proba = stack_val
        final_oof_proba = stack_oof
    elif best_name == "EasyEnsemble":
        final_val_proba = ee_model.predict_proba(X_val)[:,1]
        final_oof_proba = ee_best["oof"]
    else:
        final_val_proba = best_model.predict_proba(X_val)[:,1]
        # 위 3개의 oof 는 individual 에서
        idx = {"XGBoost":"xgb","LightGBM":"lgb","CatBoost":"cb"}[best_name]
        final_oof_proba = individual[idx]["oof_proba"]

    thr_youden = evaluate(y_dev, final_oof_proba, threshold_method="youden")["threshold"]
    thr_fbeta  = evaluate(y_dev, final_oof_proba, threshold_method="fbeta1.5")["threshold"]
    val_youden = evaluate(y_val, final_val_proba, threshold=thr_youden)
    val_fbeta  = evaluate(y_val, final_val_proba, threshold=thr_fbeta)
    print(f"  threshold[youden ]={thr_youden:.3f}  val sens={val_youden['sensitivity']:.3f} "
          f"spec={val_youden['specificity']:.3f} f1={val_youden['f1']:.3f}")
    print(f"  threshold[fbeta1.5]={thr_fbeta :.3f}  val sens={val_fbeta ['sensitivity']:.3f} "
          f"spec={val_fbeta ['specificity']:.3f} f1={val_fbeta ['f1']:.3f}")
    # 의료 도메인: 민감도 우선 → fbeta1.5 가 sens 더 높으면 채택
    if val_fbeta["sensitivity"] > val_youden["sensitivity"] and val_fbeta["auc"] >= val_youden["auc"] - 0.01:
        final_threshold = thr_fbeta; final_val = val_fbeta; thr_method = "fbeta1.5"
    else:
        final_threshold = thr_youden; final_val = val_youden; thr_method = "youden"
    print(f"  >>> 채택: threshold_method={thr_method} threshold={final_threshold:.4f}")

    # ── 8) 저장 ─────────────────────────────────────────────
    elapsed_total = time.time() - t_start
    print(f"\n  총 소요시간: {elapsed_total/60:.1f}분")

    # pkl 패키징
    with open(os.path.join(out_dir, "dataset_meta.json"), encoding="utf-8") as f:
        dataset_meta = json.load(f)

    pkg = {
        "model":         best_model if best_name != "Stacking" else None,
        "model_type":    best_name,
        "imputer":       imputer,
        "scaler":        scaler,
        "features":      list(feat_cols),
        "feature_groups": dataset_meta.get("feature_groups", {}),
        "threshold":     float(final_threshold),
        "performance":   final_val,
        "version":       "v2.2-debias",
        "debias": {
            "features": DEBIAS_FEATURES,
            "monotone_constraint": "+1",
            "feature_weight": 0.5,
            "sample_weight_cap": debias_cap,
        },
        "threshold_method": thr_method,
    }
    if best_name == "Stacking":
        pkg["stacking"] = {
            "base_models": {"xgb": best_xgb, "lgb": best_lgb, "cb": best_cb},
            "meta_model":  meta,
            "base_order":  ["xgb", "lgb", "cb"],
        }
    pkl_path = os.path.join(out_dir, "model.pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump(pkg, f)

    # 비교표 저장
    summary = {
        "version":   "v2.2-debias",
        "disease":   disease,
        "n_trials":  n_trials,
        "elapsed_minutes": round(elapsed_total/60, 2),
        "selected_model":  best_name,
        "final_threshold": float(final_threshold),
        "threshold_method": thr_method,
        "final_val_metrics": final_val,
        "comparison": [
            {"model": name, "oof_auc": oof_m["auc"], "val_auc": val_m["auc"],
             "val_sensitivity": val_m["sensitivity"], "val_specificity": val_m["specificity"],
             "val_f1": val_m["f1"]}
            for name, _, oof_m, val_m in candidates
        ],
        "best_params": {
            "xgb": studies["xgb"].best_params,
            "lgb": studies["lgb"].best_params,
            "cb":  studies["cb" ].best_params,
        },
        "n_features": len(feat_cols),
        "features":   list(feat_cols),
        "feature_groups": dataset_meta.get("feature_groups", {}),
        "debias": pkg["debias"],
    }
    with open(os.path.join(out_dir, "training_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  → pkl 저장: {pkl_path}")
    print(f"  → summary 저장: {os.path.join(out_dir, 'training_summary.json')}")
    print("=" * 78)
    return summary
