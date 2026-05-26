# DB-care 19명 환자 ML 감사 결과

- 입력: `C:\DangBom_project\병원_데이터_양식 (1)_민 수정.csv`
- 상세 CSV: `C:\DangBom_project\공통_전처리\audit_19_patients_results.csv`
- 전체 19명 중 현행 공통 30/60 컷오프 기준 저위험: 4명
- 임상 안전망 룰 적용 시 상향 필요: 7명

## 모델 임계값

| 모델 | 저장 threshold | 현행 등급 컷오프 | 관찰 |
|---|---:|---:|---|
| 망막병증 | 19.5% | 30%/60% | 저장 threshold는 predict_single/_classify_risk에서 사용되지 않음 |
| 신장질환 | 43.7% | 30%/60% | 저장 threshold는 predict_single/_classify_risk에서 사용되지 않음 |
| 심혈관 | 54.6% | 30%/60% | 저장 threshold는 predict_single/_classify_risk에서 사용되지 않음 |

## 의료진 지적 3명

| 차트 | 이름 | HbA1c | C-pep | 유병 | 현행 전체 | threshold 전체 | 안전망 후 | 점수(망막/신장/심혈관) | 안전망 사유 |
|---|---|---:|---:|---:|---|---|---|---|---|
| D2867 | 고승권 | 9.3 | 0.23 | 4 | 저위험 | 저위험 | 중위험 | 5.3/25.0/22.1 | HbA1c >= 9.0; C-peptide < 0.5; HbA1c >= 8.0 and C-peptide < 0.7 |
| D3005 | 권선호 | 13.9 | 1.32 | 10 | 저위험 | 저위험 | 고위험 | 2.1/24.9/29.3 | HbA1c >= 9.0; HbA1c >= 11.0; HbA1c >= 8.5 and DM duration >= 10y |
| D2862 | 하정아 | 8.7 | 0.48 | 17 | 저위험 | 중위험 | 중위험 | 26.1/24.8/28.3 | C-peptide < 0.5; HbA1c >= 8.0 and C-peptide < 0.7; HbA1c >= 8.5 and DM duration >= 10y |

## 현행 저위험 환자

| 차트 | 이름 | HbA1c | C-pep | 유병 | 망막 | 신장 | 심혈관 | 안전망 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| D2867 | 고승권 | 9.3 | 0.23 | 4 | 5.3 | 25.0 | 22.1 | 중위험 (HbA1c >= 9.0; C-peptide < 0.5; HbA1c >= 8.0 and C-peptide < 0.7) |
| D3096 | 김성복 | 11.2 | 1.15 | 0 | 1.1 | 22.7 | 20.0 | 고위험 (HbA1c >= 9.0; HbA1c >= 11.0) |
| D3005 | 권선호 | 13.9 | 1.32 | 10 | 2.1 | 24.9 | 29.3 | 고위험 (HbA1c >= 9.0; HbA1c >= 11.0; HbA1c >= 8.5 and DM duration >= 10y) |
| D2862 | 하정아 | 8.7 | 0.48 | 17 | 26.1 | 24.8 | 28.3 | 중위험 (C-peptide < 0.5; HbA1c >= 8.0 and C-peptide < 0.7; HbA1c >= 8.5 and DM duration >= 10y) |

## 의료진 지적 3명 로컬 영향도

양수는 해당 환자 점수를 올린 변수, 음수는 낮춘 변수입니다. 기준값은 모델 imputer의 학습 중앙/최빈값입니다.

### D2867 고승권
- 망막병증: DM_medication -38.89p(0 -> ref ), exercise -14.41p(0 -> ref ), smoking -7.02p(0 -> ref ), drinking -5.47p(0 -> ref ), insulin_medication +3.73p(1 -> ref ), sleep_7h -3.66p(1 -> ref ), HE_ast -2.77p(32 -> ref ), HOMA_beta -2.51p(0.62 -> ref )
- 신장질환: HE_Usg +2.00p(1.01 -> ref ), eGFR -1.21p(111.86 -> ref ), insulin_medication +1.20p(1 -> ref ), HE_Upro_pos -1.20p(0 -> ref ), exercise -0.90p(0 -> ref ), HE_wt -0.72p(52.3 -> ref ), DM_duration -0.70p(4 -> ref ), LDL_calc -0.54p(133 -> ref )
- 심혈관: age -5.10p(52 -> ref ), DM_duration -1.30p(4 -> ref ), HE_chol +1.17p(192 -> ref ), HE_alt -0.88p(25 -> ref ), HE_crea -0.44p(0.65 -> ref ), eGFR -0.40p(111.86 -> ref ), HE_ast +0.22p(32 -> ref ), DBP -0.10p(77 -> ref )

### D3005 권선호
- 망막병증: exercise -44.98p(0 -> ref ), DM_medication -19.78p(0 -> ref ), hypertension -3.67p(0 -> ref ), drinking -2.57p(1 -> ref ), smoking -2.14p(0 -> ref ), HE_HDL_st2 +0.65p(80 -> ref ), HE_Uph -0.65p(6 -> ref ), HE_ast -0.58p(35 -> ref )
- 신장질환: sex -2.76p(1 -> ref ), drinking -1.73p(1 -> ref ), HE_Usg +1.34p(1 -> ref ), HE_TG +0.83p(53 -> ref ), TyG_index -0.74p(8.97 -> ref ), HE_crea -0.69p(0.61 -> ref ), exercise -0.68p(0 -> ref ), DBP -0.49p(84 -> ref )
- 심혈관: HE_chol -8.11p(186 -> ref ), age +3.07p(60 -> ref ), sex +1.51p(1 -> ref ), DM_duration +0.34p(10 -> ref ), HE_glu -0.34p(296 -> ref ), HE_crea -0.28p(0.61 -> ref ), HE_BMI +0.27p(20 -> ref ), HE_wt -0.25p(56.2 -> ref )

### D2862 하정아
- 망막병증: exercise -51.79p(1 -> ref ), hypertension -42.25p(0 -> ref ), DM_medication -25.26p(1 -> ref ), sleep_7h -18.88p(1 -> ref ), drinking -17.40p(0 -> ref ), HE_Uglu_pos -13.92p(1 -> ref ), HE_Uph -9.29p(6 -> ref ), HE_chol -4.62p(170 -> ref )
- 신장질환: hypertension -4.10p(0 -> ref ), HE_wt -2.47p(53.6 -> ref ), HE_Usg +2.03p(1 -> ref ), HE_BMI -1.73p(21.7 -> ref ), drinking -1.11p(0 -> ref ), HE_glu -0.78p(161 -> ref ), HE_ht +0.60p(157.2 -> ref ), HE_Uph +0.52p(6 -> ref )
- 심혈관: hypertension -7.20p(0 -> ref ), HE_alt -1.57p(24 -> ref ), age -1.32p(55 -> ref ), DM_duration +1.27p(17 -> ref ), LDL_calc -0.92p(100 -> ref ), HE_glu -0.12p(161 -> ref ), HE_BMI +0.12p(21.7 -> ref ), sex +0.00p(2 -> ref )

## 전역 feature_importances 상위

### 망막병증
insulin_medication 28.05%, exercise 9.12%, sleep_7h 5.25%, HE_HbA1c 4.24%, DM_medication 3.85%, BMI_HOMA_IR 3.80%, DM_duration 3.28%, HE_crea 2.25%

### 신장질환
HE_crea 7.42%, eGFR 6.46%, HE_BMI 5.41%, HE_HDL_st2 4.60%, HE_glu 4.52%, DM_diagnosis_age 4.36%, HE_Usg 4.36%, DBP 4.33%

### 심혈관
사용 가능한 feature_importances 없음

## 핵심 결론

1. 현행 등급화는 모델별 학습 threshold를 무시하고 score 30/60만 사용합니다.
2. 망막병증은 저장 threshold가 약 19.5%라서 20~29점 환자가 임계값상 양성인데도 화면에서는 저위험이 됩니다.
3. DKD/CVD 모델은 C_peptide를 직접 feature로 쓰지 않고 TyG만 쓰므로 저 C-peptide 위험을 구조적으로 반영하지 못합니다.
4. 저 C-peptide + 고 HbA1c + 긴 유병기간 조합은 ML 후처리 임상 안전망 룰로 최소 중위험 이상 보정해야 합니다.