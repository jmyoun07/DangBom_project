# 기존 3개 모델(망막병증/DKD/심혈관) ML 방법론 & 변수 종합 정리

> 출처: `병원_데이터_양식` · `dataset_meta.json` · `training_summary.json` · `train_debias_common.py`
> 작성일: 2026-05-20
> 버전: v2.2-debias

신경병증 모델 설계 시 이 구조를 그대로 재사용한다.

---

## 1. 데이터 출처 (3개 모델 공통)

| 항목 | 내용 |
|------|------|
| **원천 DB** | KNHANES (국민건강영양조사) HN16~HN24 .sav 파일 |
| **포함 연도** | DR: HN19~21 (3년) / DKD: HN19~24 (6년) / CVD: HN19~21+HN24 (4년) |
| **연도가 다른 이유** | 종속변수(DH7_dg / DN1_dg / DI3-DI6_dg) 가 일부 연도 미수집 |
| **당뇨환자 필터** | `DE1_dg==1 OR HbA1c≥6.5 OR 공복혈당≥126` (ADA 기준) |
| **분할 방식** | sklearn `train_test_split(test_size=0.2, stratify=y, random_state=42)` |
| **데이터 누수 방지** | dev (학습용) / val (검증용) 완전 분리, val 에는 어떤 전처리 fit 도 안 함 |

### 최종 학습 샘플 수

| 모델 | 전체 N | 양성 N | 유병률 | dev/val |
|------|--------|--------|--------|---------|
| 망막병증 (DR) | 2,694 | 104 | 3.86% | 2,155 / 539 |
| 신장질환 (DKD) | 4,985 | 136 | 2.73% | 3,988 / 997 |
| 심혈관 (CVD) | 3,485 | 433 | 12.42% | 2,788 / 697 |

---

## 2. 종속변수(타겟) 정의

모두 **KNHANES 의사진단(`*_dg`) 변수** 기반의 binary classification.

```python
# 망막병증 (DR) — 의사진단 OR 안저검사 양성 (HN19~21 만 존재)
target_DR = (DH7_dg == 1) OR (E_DM == 1)

# 신장질환 (DKD) — 의사진단 단독
target_DKD = (DN1_dg == 1)

# 심혈관 (CVD) — 4개 진단의 union (어느 하나라도 양성이면 1)
target_CVD = (DI3_dg == 1)  # 뇌졸중
            OR (DI4_dg == 1)  # 심근경색·협심증
            OR (DI5_dg == 1)  # 이상지질혈증
            OR (DI6_dg == 1)  # 고혈압
```

> **종속변수 결측 처리**: 0/1 둘 다 아닌 값(8=비해당, 9=무응답) → NaN 으로 제거, 학습에서 완전 배제.

---

## 3. 독립변수 (DR=42개 / DKD=CVD=38개)

11개 카테고리. C-peptide 4종(`C_peptide, HOMA_IR, HOMA_beta, BMI_HOMA_IR`)은 **DR 전용** — 이유는 HN22+ 부터 KNHANES 가 HE_insulin 측정을 중단했기 때문.

| 카테고리 | 변수 (DR/DKD/CVD 공통) | DR 추가 | 비고 |
|---------|----------------------|---------|------|
| **인구통계 (2)** | age, sex | — | |
| **당뇨 관련 (4)** | DM_duration, DM_diagnosis_age, DM_medication, insulin_medication | — | DE1_31/32 매핑 |
| **혈당 (2)** | HE_glu, HE_HbA1c | + C_peptide | DR만 C-펩 포함 |
| **인슐린 저항성 파생 (1~4)** | TyG_index | + HOMA_IR, HOMA_beta, BMI_HOMA_IR | DR 4개 / DKD·CVD 1개 |
| **지질 (5)** | HE_chol, HE_HDL_st2, HE_TG, LDL_calc, non_HDL | — | |
| **신장 (2)** | HE_crea, eGFR | — | CKD-EPI 공식 |
| **혈압 (4)** | SBP, DBP, pulse_pressure, hypertension | — | |
| **신체 계측 (3)** | HE_BMI, HE_ht, HE_wt | — | |
| **간효소 (2)** | HE_ast, HE_alt | — | |
| **소변 dipstick (9)** | HE_Upro_pos, HE_Uglu_pos, HE_Ubld_pos, HE_Ubil_pos, HE_Uro_abn, HE_Uket_pos, HE_Unitr_b, HE_Uph, HE_Usg | — | ≥2 → 1.0 binary |
| **생활습관 (4)** | smoking, drinking, exercise, sleep_7h | — | DI1/sm_presnt/dr_month/pa_aerobic |
| **합계** | **38** | **+4** | DR=42 |

### 핵심 파생 공식

```python
DM_duration    = age - DE1_ag                     # 당뇨 이환기간
SBP            = mean(HE_sbp2, HE_sbp3)           # 1차 측정 제외
DBP            = mean(HE_dbp2, HE_dbp3)
pulse_pressure = SBP - DBP

# 인슐린 저항성 (DR 전용, C_peptide 환산)
C_peptide   = HE_insulin / 3.0                    # 임상 근사
HOMA_IR     = (HE_glu × C_peptide) / 405
HOMA_beta   = (360 × C_peptide) / (HE_glu - 63)
BMI_HOMA_IR = HE_BMI × HOMA_IR
TyG_index   = ln(HE_TG × HE_glu / 2)

# 지질
non_HDL  = HE_chol - HE_HDL_st2
LDL_calc = HE_chol - HE_HDL_st2 - HE_TG/5         # Friedewald

# eGFR (CKD-EPI, 성별 보정)
eGFR = 141 × min(Scr/κ,1)^α × max(Scr/κ,1)^-1.209 × 0.993^age × (1.018 if 여)
       # 남: κ=0.9, α=-0.411  /  여: κ=0.7, α=-0.329

# 소변 binary
HE_Upro_pos = 1 if HE_Upro >= 2 else 0            # dipstick ≥ ++ 양성

# 수면
sleep_hours = (5×주중 + 2×주말) / 7
sleep_7h    = 1 if sleep_hours >= 7 else 0
```

---

## 4. 전처리 파이프라인

3개 모델 공통. **dev 에서만 fit, val 에는 transform 만 적용** (data leakage 방지).

```python
imputer = KNNImputer(n_neighbors=5)               # 결측 보간
scaler  = StandardScaler()                        # z-normalization (평균 0, 분산 1)

X_dev = scaler.fit_transform(imputer.fit_transform(X_dev_raw))
X_val = scaler.transform(imputer.transform(X_val_raw))  # fit 절대 안 함
```

### 불균형 대응 (모델별로 다름)

| 모델 | 방법 | 이유 |
|------|------|------|
| DR | **BorderlineSMOTE** (k=5, fallback=SMOTE) | 양성 83개라 소수, 결정경계 부근 합성 |
| DKD | scale_pos_weight (XGB/LGB) + class_weight='balanced' (LR meta) | 양성 109개 |
| CVD | **EasyEnsemble** (n_estimators=50, AdaBoost base) | 음성 다운샘플링 → bagging, 양성 346 |

---

## 5. 모델 아키텍처

### 5.1 DR (망막병증) — XGBoost 단일

```python
XGBClassifier(
    n_estimators=300, max_depth=4, learning_rate=0.03,
    subsample=0.8, colsample_bytree=0.8,
    min_child_weight=3, gamma=0.1,
    reg_alpha=0.5, reg_lambda=1.0,
    random_state=42, eval_metric='logloss',
)
# 학습: model.fit(X_dev_smote, y_dev_smote)
# 임계값: Youden's J on dev OOF
```

### 5.2 DKD (신장질환) — Stacking 앙상블

```
         X (38 features)
              ↓
    ┌─────────┼──────────┐
    ↓         ↓          ↓
  XGBoost  LightGBM  CatBoost          ← 3 base 모델
    │         │          │             ← 모두 5-fold OOF predict_proba
    └─────────┼──────────┘
              ↓
       [p_xgb, p_lgb, p_cb]
              ↓
   LogisticRegression(class_weight='balanced')   ← meta-learner
              ↓
         최종 확률
```

### 5.3 CVD (심혈관) — EasyEnsemble

```python
EasyEnsembleClassifier(
    n_estimators=50,                            # 50개 bagging
    estimator=AdaBoostClassifier(n_estimators=10, algorithm='SAMME'),
    # 각 bag = 음성 다운샘플링 + AdaBoost
)
```

---

## 6. 학습 절차 (DKD·CVD 공통 — `train_debias_common.py`)

### 6.1 하이퍼파라미터 튜닝

```python
optuna.create_study(
    direction='maximize',
    sampler=TPESampler(seed=42, n_startup_trials=20),
    pruner=MedianPruner(n_startup_trials=10, n_warmup_steps=2),
)
# 3개 알고리즘 각각 150 trials × 5-fold CV
# 평가지표: 5-fold OOF AUC (val 에 오버피팅 방지)
```

### 6.2 역인과(reverse causation) 완화 — DKD/CVD 전용

`insulin_medication` 과 `DM_medication` 은 "병이 심한 사람이 약을 더 많이 쓴다" 는 역인과 관계가 있어, 모델이 잘못 학습할 위험. 3중 처리:

| 처리 | 적용 | 효과 |
|------|------|------|
| **monotone_constraint = +1** | XGB/LGB/CB 모두 | 약 복용 → 위험도 ↑ 방향만 허용 |
| **feature_weight = 0.5** | XGB (feature_weights 인자) | tree split 시 선택 빈도 50% 감소 |
| **sample_weight = 0.7** | 약 복용 양성 샘플 | 학습 영향력 30% 감소 |

### 6.3 임계값(threshold) 선정

```python
# 두 방법 비교
thr_youden = argmax(sensitivity + specificity - 1) on dev OOF
thr_fbeta  = argmax(F_β=1.5 score) on dev OOF        # 민감도 가중

# 의료 도메인: 민감도 우선
if val_fbeta.sens > val_youden.sens AND val_fbeta.auc >= val_youden.auc - 0.01:
    채택 = fbeta1.5
else:
    채택 = youden
```

### 6.4 모델 선정 기준

OOF AUC (out-of-fold 평균) 가 가장 높은 것 → 검증셋 성능에 끌려가지 않음.

```python
candidates = [XGBoost, LightGBM, CatBoost, Stacking, EasyEnsemble]
best = max(candidates, key=lambda c: c.oof_auc)
```

---

## 7. 최종 성능 (held-out validation)

| 모델 | 알고리즘 | AUC | Sensitivity | Specificity | F1 | 임계값 |
|------|---------|-----|-------------|-------------|-----|--------|
| **DR** | XGBoost | **0.843** | 0.524 | 0.931 | 0.324 | 0.195 |
| **DKD** | Stacking (XGB+LGB+CB→LR) | **0.752** | 0.630 | 0.694 | 0.100 | 0.437 |
| **CVD** | EasyEnsemble (n=50) | **0.761** | 0.667 | 0.703 | 0.356 | 0.546 |

---

## 8. 모델 패키지 구조 (.pkl 저장 형식)

```python
{
    'model':         <best_model>,                # Stacking 일 땐 None
    'model_type':    'XGBoost' | 'Stacking' | 'EasyEnsemble',
    'imputer':       KNNImputer(...),             # fit 된 객체
    'scaler':        StandardScaler(...),         # fit 된 객체
    'features':      [...],                       # 변수 순서 (predict 시 동일)
    'feature_groups': {...},                      # UI 그룹화용
    'threshold':     0.437,                       # 최종 채택 임계값
    'performance':   {...},                       # val 메트릭
    'version':       'v2.2-debias',
    'debias': {
        'features': ['insulin_medication', 'DM_medication'],
        'monotone_constraint': '+1',
        'feature_weight': 0.5,
        'sample_weight_cap': 0.7,
    },
    'threshold_method': 'youden' | 'fbeta1.5',
    # Stacking 일 때만:
    'stacking': {
        'base_models': {'xgb':..., 'lgb':..., 'cb':...},
        'meta_model':  LogisticRegression(...),
        'base_order':  ['xgb', 'lgb', 'cb'],
    },
}
```

---

## 9. 신경병증 모델에 그대로 가져갈 항목

| 항목 | 재사용 여부 | 비고 |
|------|------------|------|
| 38 변수 (DKD 와 동일) | ✅ 그대로 | C-peptide 4종은 못 씀 (HN22+ 결측) |
| 당뇨환자 필터 | ✅ 그대로 | `DE1_dg==1 OR HbA1c≥6.5 OR glu≥126` |
| KNNImputer + StandardScaler | ✅ 그대로 | |
| 역인과 완화 (insulin/DM_medication) | ✅ 그대로 | 신경병증도 같은 역인과 존재 |
| Optuna 150 trials × 3 algo + Stacking + EasyEnsemble | ✅ 그대로 | `train_debias_common.py` 호출 |
| Youden vs Fβ1.5 임계값 선정 | ✅ 그대로 | |
| **종속변수 정의** | ❌ **새로 설계 필요** | **이것만 결정되면 즉시 학습 가능** |
| 사용 연도 | ❓ 종속변수 가용 연도에 따라 결정 | LQ_2HT/LQ_4EQL 은 HN19~24 다 있음 |

---

**즉, 종속변수 정의만 정해지면 다음 한 줄로 학습이 끝난다.**

```python
from train_debias_common import run_debias_training
run_debias_training(disease="DPN", out_dir="신경병증", n_trials=150)
```

---

## 10. 관련 파일 참조

| 파일 | 역할 |
|------|------|
| `공통_전처리/build_unified_dataset_v2.py` | KNHANES → development.csv / validation.csv 생성 |
| `공통_전처리/train_common.py` | DR 학습 보조 함수 (전처리·평가·저장) |
| `공통_전처리/train_debias_common.py` | DKD·CVD 통합 학습 파이프라인 |
| `망막병증/train_model.py` | DR XGBoost 학습 스크립트 |
| `신장질환/train_model.py` | DKD Stacking 학습 entry point |
| `심혈관/train_model.py` | CVD EasyEnsemble 학습 entry point |
| `{질환}/dataset_meta.json` | 데이터셋 메타데이터 (변수·N·유병률) |
| `{질환}/training_summary.json` | 학습 결과 (성능·하이퍼파라미터·feature importance) |
| `{질환}/model.pkl` | 최종 모델 패키지 |
| `backend/ml/predictor.py` | 런타임 추론 (3개 모델 통합 로딩 + 위험도 보정) |
