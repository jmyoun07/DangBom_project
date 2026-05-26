"""
심혈관 (CVD) 재학습 v2.2-debias

목표:
- AUC 향상: Optuna 150 trials × XGB/LGB/CB + Stacking + EasyEnsemble 비교
- 데이터 불균형: scale_pos_weight (CVD prevalence ~12%, 약한 불균형)
- Threshold: Youden's J vs F-beta1.5 비교 후 자동 선정
- 역인과 완화: insulin_medication / DM_medication 에 monotonic+1, feature_weight=0.5,
              sample_weight cap 0.7

실행:
    python 심혈관/retrain_v2_debias.py
"""
import os
import sys

THIS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(THIS, ".."))
sys.path.insert(0, os.path.join(ROOT, "공통_전처리"))

from train_debias_common import run_debias_training

if __name__ == "__main__":
    summary = run_debias_training(
        disease="CVD",
        out_dir=THIS,
        n_trials=150,
        debias_cap=0.7,
    )
    print("\n[FINAL] 심혈관 학습 완료")
    print(f"  selected: {summary['selected_model']}")
    print(f"  val AUC : {summary['final_val_metrics']['auc']:.4f}")
    print(f"  val sens: {summary['final_val_metrics']['sensitivity']:.3f}")
    print(f"  val spec: {summary['final_val_metrics']['specificity']:.3f}")
