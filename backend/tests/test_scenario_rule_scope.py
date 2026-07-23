import unittest
from types import SimpleNamespace
from unittest.mock import patch

from routers import scenario


FULL_NAMES = (
    "neuropathy",
    "retinopathy",
    "kidney_disease",
    "cardiovascular",
    "cerebrovascular",
    "dementia",
)


def _predictions(score=20.0):
    return {
        name: {
            "score": score,
            "raw_score": score,
            "display_score": score,
            "level": "저위험",
            "available": True,
            "risk_source": "ml_model",
            "risk_sources": ["ml_model"],
            "clinical_flags": [],
        }
        for name in FULL_NAMES
    }


def _unavailable_high_predictions():
    return {
        name: {
            "score": None,
            "raw_score": None,
            "display_score": None,
            "level": "고위험",
            "available": False,
            "risk_source": "clinical_floor",
            "risk_sources": ["clinical_floor"],
            "clinical_floor_reasons": ["Rule 5: eGFR 40.0 < 45"],
            "clinical_flags": [],
        }
        for name in FULL_NAMES
    }


def _classify(score, *_args, **_kwargs):
    if score >= 60:
        return "고위험"
    if score >= 30:
        return "중위험"
    return "저위험"


def _patient_data():
    return {
        "id": 1,
        "age": 60,
        "sex": "M",
        "hba1c": 7.0,
        "fbg": 110.0,
        "c_peptide": 2.0,
        "total_cholesterol": 250.0,
        "triglycerides": 120.0,
        "hdl": 50.0,
        "ldl": 200.0,
        "cr": 1.0,
        "egfr": 80.0,
        "sbp": 130.0,
        "dbp": 80.0,
        "bmi": 24.0,
        "height": 170.0,
        "weight": 70.0,
        "dm_duration": 5.0,
    }


class ScenarioRuleScopeTests(unittest.TestCase):
    def test_build_scenario_uses_rules_1_to_5_in_all_four_paths(self):
        pdict = _patient_data()
        patient = SimpleNamespace(**pdict)
        empty_floors = {name: None for name in FULL_NAMES}

        with (
            patch.object(
                scenario,
                "predict_with_simulation",
                return_value=_predictions(20.0),
            ) as predict_sim,
            patch.object(
                scenario,
                "predict_all",
                return_value=_predictions(10.0),
            ) as predict_all,
            patch.object(
                scenario,
                "clinical_floor_levels",
                return_value=empty_floors,
            ) as floor_levels,
            patch.object(scenario, "get_disease_threshold", return_value=30.0),
            patch.object(scenario, "classify_disease_risk", side_effect=_classify),
            patch.object(
                scenario,
                "get_disease_thresholds",
                return_value={name: 30.0 for name in FULL_NAMES},
            ),
        ):
            payload = scenario.build_scenario_payload(
                patient,
                pdict,
                age=60,
                sim_hba1c=7.0,
                sim_cpep=2.0,
                base_hba1c=7.0,
                base_cpep=2.0,
            )

        expected = scenario.SCENARIO_CLINICAL_FLOOR_RULES
        self.assertEqual(predict_sim.call_args.kwargs["enabled_rules"], expected)
        self.assertEqual(predict_all.call_args.kwargs["enabled_rules"], expected)
        self.assertEqual(floor_levels.call_count, 2)
        for call in floor_levels.call_args_list:
            self.assertEqual(call.kwargs["enabled_rules"], expected)
        self.assertEqual(payload["meta"]["excluded_floor_rules"], [6, 7])
        self.assertEqual(
            payload["meta"]["floor_policy_note"],
            scenario.SCENARIO_FLOOR_POLICY_NOTE,
        )

    def test_insufficient_response_keeps_policy_metadata(self):
        insufficient = {
            name: {
                "risk_source": "insufficient_data",
                "missing_required": ["공복혈당"],
            }
            for name in FULL_NAMES
        }
        pdict = _patient_data()
        patient = SimpleNamespace(**pdict)
        with patch.object(
            scenario,
            "predict_with_simulation",
            return_value=insufficient,
        ):
            payload = scenario.build_scenario_payload(
                patient,
                pdict,
                age=60,
                sim_hba1c=7.0,
                sim_cpep=2.0,
                base_hba1c=7.0,
                base_cpep=2.0,
            )

        self.assertTrue(payload["insufficient"])
        self.assertEqual(payload["meta"]["excluded_floor_rules"], [6, 7])
        self.assertEqual(
            payload["meta"]["floor_policy_note"],
            scenario.SCENARIO_FLOOR_POLICY_NOTE,
        )

    def test_rule_5_survives_unavailable_heuristic_paths(self):
        pdict = _patient_data()
        pdict["egfr"] = 40.0
        patient = SimpleNamespace(**pdict)
        high_floors = {name: "고위험" for name in FULL_NAMES}

        with (
            patch.object(
                scenario,
                "predict_with_simulation",
                return_value=_unavailable_high_predictions(),
            ),
            patch.object(
                scenario,
                "predict_all",
                return_value=_unavailable_high_predictions(),
            ),
            patch.object(
                scenario,
                "clinical_floor_levels",
                return_value=high_floors,
            ),
            patch.object(scenario, "get_disease_threshold", return_value=30.0),
            patch.object(scenario, "classify_disease_risk", side_effect=_classify),
            patch.object(
                scenario,
                "get_disease_thresholds",
                return_value={name: 30.0 for name in FULL_NAMES},
            ),
        ):
            payload = scenario.build_scenario_payload(
                patient,
                pdict,
                age=60,
                sim_hba1c=7.0,
                sim_cpep=2.0,
                base_hba1c=7.0,
                base_cpep=2.0,
            )

        for short_name in ("kidney", "retina", "cardio", "neuro", "dementia", "cerebro"):
            self.assertEqual(payload["radar"][short_name]["level"], "고위험")
            self.assertEqual(
                payload["neglect"]["complications"][short_name]["level"],
                "고위험",
            )
            self.assertEqual(
                payload["intensive"]["complications"][short_name]["level"],
                "고위험",
            )
            self.assertEqual(
                payload["graduation"]["complications"][short_name]["level"],
                "고위험",
            )


if __name__ == "__main__":
    unittest.main()
