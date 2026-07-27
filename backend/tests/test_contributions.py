"""환자별 변수 기여도(SHAP) 안전장치 테스트.

이 기능은 잘못 만들면 '고정 표시'보다 더 나쁜 오정보가 된다. 실제로 제한 없이
SHAP 을 돌리면 망막병증 1순위가 전 환자 '운동'으로 나왔다 — 병원이 운동을
수집하지 않아(625명 중 0건) imputer 가 채운 값이 기여도를 독식했기 때문이다.

따라서 다음을 강제한다:
  1) 병원이 수집하지 않는 변수(운동·수면·흡연·음주·소변)는 절대 후보가 아니다
  2) 질환별로 임상적으로 설명 가능한 변수만 제시한다
  3) 실측이 없는(결측→imputer) 값은 근거로 쓰지 않는다
  4) 미지원 모델에서는 None 을 반환해 UI 가 기존 고정 표시로 폴백한다

실행: PYTHONPATH=backend python backend/tests/test_contributions.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from ml.contributions import (  # noqa: E402
    CLINICAL_FEATURES,
    FEATURE_LABELS,
    MEASURED_FEATURES,
    compute_contributions,
)

# 병원이 수집하지 않는 변수 — 실데이터 625명 중 입력 0건 (2026-07 확인)
NEVER_COLLECTED = {
    "exercise", "sleep_7h", "sleep_hours", "smoking", "drinking",
    "HE_Upro_pos", "HE_Uglu_pos", "HE_Ubld_pos", "HE_Ubil_pos",
    "HE_Uket_pos", "HE_Uro_abn", "HE_Unitr_b", "HE_Uph", "HE_Usg",
    "DM_medication", "insulin_medication",
}


class ContributionsSafetyTest(unittest.TestCase):
    def test_uncollected_features_never_candidates(self):
        """미수집 변수가 후보에 있으면 imputer 가 채운 가짜 값이 1순위가 된다."""
        leaked = NEVER_COLLECTED & MEASURED_FEATURES
        self.assertEqual(
            leaked, set(),
            f"병원이 수집하지 않는 변수가 후보에 포함됨: {leaked} — "
            "imputer 가 채운 값이 '1순위 요인'으로 표시되어 오정보가 됩니다.",
        )

    def test_clinical_whitelist_subset_of_measured(self):
        """질환별 화이트리스트도 실측 범위를 벗어나면 안 된다."""
        for disease, feats in CLINICAL_FEATURES.items():
            outside = feats - MEASURED_FEATURES
            self.assertEqual(
                outside, set(),
                f"{disease} 화이트리스트에 미실측 변수 {outside} 포함",
            )

    def test_every_disease_has_whitelist(self):
        for d in ("retinopathy", "kidney_disease", "cardiovascular",
                  "neuropathy", "cerebrovascular", "dementia"):
            self.assertIn(d, CLINICAL_FEATURES, f"{d} 임상 화이트리스트 누락")

    def test_all_candidates_have_korean_labels(self):
        """화면에 영문 변수명(HE_HbA1c)이 그대로 노출되면 안 된다."""
        missing = [f for f in MEASURED_FEATURES if f not in FEATURE_LABELS]
        self.assertEqual(missing, [], f"한글 라벨 없는 변수: {missing}")

    def test_unsupported_model_returns_none(self):
        """Stacking·EasyEnsemble 등 미지원 모델은 None → UI 가 고정 표시로 폴백."""
        self.assertIsNone(compute_contributions("kidney_disease", {}, None, {}))
        self.assertIsNone(
            compute_contributions("kidney_disease", {"model": None, "features": ["a"]},
                                  np.zeros((1, 1)), {}))

    def test_real_model_returns_patient_specific_reasons(self):
        """실제 모델에서 기여도가 나오고, 결측 변수는 근거로 쓰이지 않는다."""
        import joblib

        pkg_path = Path(__file__).resolve().parent.parent / "ml" / "models" / "retinopathy_model.pkl"
        if not pkg_path.exists():
            self.skipTest("retinopathy_model.pkl 없음")
        pkg = joblib.load(pkg_path)
        feats = pkg["features"]

        # C-peptide·HbA1c 등 핵심만 채우고 나머지는 결측(NaN)
        raw = {f: np.nan for f in feats}
        raw.update({"age": 62, "HE_HbA1c": 9.8, "HE_glu": 180, "C_peptide": 0.7,
                    "SBP": 150, "DBP": 90, "HE_crea": 1.3, "eGFR": 55,
                    "HE_BMI": 27.0, "HE_TG": 220, "HE_HDL_st2": 38})
        X = np.array([[raw.get(f, np.nan) for f in feats]], dtype=float)
        X = pkg["imputer"].transform(X)
        if pkg.get("scaler") is not None:
            X = pkg["scaler"].transform(X)

        out = compute_contributions("retinopathy", pkg, X, raw)
        self.assertTrue(out, "실제 모델에서 기여도가 산출되지 않음")
        allowed = CLINICAL_FEATURES["retinopathy"]
        for item in out:
            self.assertIn(item["feature"], allowed,
                          f"화이트리스트 밖 변수 노출: {item['feature']}")
            self.assertIsNotNone(item["value"],
                                 f"{item['feature']}: 실측 없는 값이 근거로 제시됨")
            self.assertIn(item["direction"], ("up", "down"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
