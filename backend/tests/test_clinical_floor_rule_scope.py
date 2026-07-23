import copy
import unittest
from unittest.mock import patch

from ml import predictor


SCENARIO_RULES = frozenset({1, 2, 3, 4, 5})


def _prediction(*, available=True, level="저위험", score=10.0):
    return {
        "score": score if available else None,
        "raw_score": score if available else None,
        "display_score": score if available else None,
        "level": level if available else None,
        "available": available,
        "risk_source": "ml_model" if available else "unavailable",
        "risk_sources": ["ml_model"] if available else [],
        "clinical_flags": [],
        "error": None if available else "model_not_loaded",
    }


def _complete_patient(**overrides):
    patient = {
        "age": 60,
        "sex": "M",
        "hba1c": 7.0,
        "fbg": 110.0,
        "c_peptide": 2.0,
        "total_cholesterol": 250.0,
        "triglycerides": 120.0,
        "hdl": 50.0,
        "ldl": 180.0,
        "cr": 1.0,
        "egfr": 80.0,
        "sbp": 130.0,
        "dbp": 80.0,
        "height": 170.0,
        "weight": 70.0,
        "dm_duration": 5.0,
    }
    patient.update(overrides)
    return patient


class ClinicalFloorRuleScopeTests(unittest.TestCase):
    def test_default_equals_explicit_all_rules(self):
        patient = _complete_patient(hba1c=9.2, sbp=165.0, ldl=210.0)
        default = {"kidney_disease": _prediction()}
        explicit = copy.deepcopy(default)

        predictor.apply_clinical_floor(default, patient)
        predictor.apply_clinical_floor(
            explicit,
            patient,
            enabled_rules=predictor.ALL_CLINICAL_FLOOR_RULES,
        )

        self.assertEqual(default, explicit)

    def test_rules_6_7_are_excluded_before_any_floor_mutation(self):
        patient = _complete_patient(sbp=160.0, dbp=100.0, ldl=190.0)
        full = {"kidney_disease": _prediction()}
        scoped = copy.deepcopy(full)

        predictor.apply_clinical_floor(full, patient)
        predictor.apply_clinical_floor(scoped, patient, enabled_rules=SCENARIO_RULES)

        self.assertEqual(full["kidney_disease"]["level"], "중위험")
        info = scoped["kidney_disease"]
        self.assertEqual(info["level"], "저위험")
        self.assertNotIn("clinical_floor_reasons", info)
        self.assertNotIn("clinical_floor", info["risk_sources"])
        self.assertNotIn(
            "severe_hypertension",
            {flag["type"] for flag in info["clinical_flags"]},
        )
        self.assertNotIn(
            "ldl_very_high",
            {flag["type"] for flag in info["clinical_flags"]},
        )
        self.assertEqual(info["score"], 10.0)
        self.assertEqual(info["raw_score"], 10.0)

    def test_rules_1_to_5_remain_enabled(self):
        cases = (
            (_complete_patient(hba1c=11.0), "고위험"),
            (_complete_patient(hba1c=9.0), "중위험"),
            (_complete_patient(c_peptide=0.99), "중위험"),
            (_complete_patient(hba1c=8.5, dm_duration=10.0), "중위험"),
            (_complete_patient(egfr=44.9), "고위험"),
        )
        for patient, expected in cases:
            with self.subTest(patient=patient, expected=expected):
                levels = predictor.clinical_floor_levels(
                    patient,
                    ["kidney_disease"],
                    enabled_rules=SCENARIO_RULES,
                )
                self.assertEqual(levels["kidney_disease"], expected)

    def test_rule_1_and_5_force_high_even_when_model_unavailable(self):
        cases = (
            _complete_patient(hba1c=11.0),
            _complete_patient(egfr=44.9),
        )
        for patient in cases:
            with self.subTest(patient=patient):
                predictions = {"kidney_disease": _prediction(available=False)}
                predictor.apply_clinical_floor(
                    predictions,
                    patient,
                    enabled_rules=SCENARIO_RULES,
                )
                info = predictions["kidney_disease"]
                self.assertFalse(info["available"])
                self.assertEqual(info["level"], "고위험")
                self.assertEqual(info["error"], "model_not_loaded")
                self.assertIn("clinical_floor", info["risk_sources"])
                self.assertTrue(info["clinical_floor_reasons"])
                self.assertTrue(info["clinical_flags"])

    def test_rule_2_still_runs_when_rule_1_is_disabled(self):
        predictions = {"kidney_disease": _prediction()}
        predictor.apply_clinical_floor(
            predictions,
            _complete_patient(hba1c=11.0),
            enabled_rules={2},
        )
        self.assertEqual(predictions["kidney_disease"]["level"], "중위험")

    def test_empty_rule_set_does_not_fall_back_to_all_rules(self):
        predictions = {"kidney_disease": _prediction()}
        predictor.apply_clinical_floor(
            predictions,
            _complete_patient(hba1c=12.0, egfr=30.0, sbp=180.0, ldl=250.0),
            enabled_rules=set(),
        )
        self.assertEqual(predictions["kidney_disease"]["level"], "저위험")
        self.assertNotIn("clinical_floor_reasons", predictions["kidney_disease"])

    def test_display_clamp_runs_after_selected_policy(self):
        patient = _complete_patient(ldl=200.0)

        def fake_predict_single(*_args, **_kwargs):
            return _prediction()

        with (
            patch.object(predictor, "predict_single", side_effect=fake_predict_single),
            patch.object(predictor, "get_disease_threshold", return_value=30.0),
            patch("services.percentile.enrich_predictions", return_value=None),
        ):
            full = predictor.predict_all(patient)
            scoped = predictor.predict_all(patient, enabled_rules=SCENARIO_RULES)

        for disease in full:
            self.assertEqual(full[disease]["level"], "중위험")
            self.assertGreaterEqual(full[disease]["display_score"], 30.0)
            self.assertEqual(scoped[disease]["level"], "저위험")
            self.assertEqual(scoped[disease]["display_score"], 10.0)
            self.assertEqual(full[disease]["score"], scoped[disease]["score"])
            self.assertEqual(full[disease]["raw_score"], scoped[disease]["raw_score"])

    def test_predict_with_simulation_forwards_enabled_rules(self):
        patient = _complete_patient()
        with patch.object(predictor, "predict_all", return_value={}) as predict_all:
            predictor.predict_with_simulation(
                patient,
                c_peptide=1.5,
                hba1c=6.5,
                enabled_rules=SCENARIO_RULES,
            )
        self.assertEqual(predict_all.call_args.kwargs["enabled_rules"], SCENARIO_RULES)


if __name__ == "__main__":
    unittest.main()
