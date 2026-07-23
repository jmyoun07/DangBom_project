"""CLINICAL_RANGES(업로드 검증) ↔ PatientBase Field(ge/le)(수기 POST/PATCH 검증) 동기화 강제.

두 정의가 어긋나면 같은 값이 한 경로에서만 거부되는 불일치(codex M5)가 생긴다.
한쪽만 바꾸면 이 테스트가 실패해 즉시 알린다.

실행: PYTHONPATH=backend python backend/tests/test_clinical_ranges_sync.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.derived import CLINICAL_RANGES  # noqa: E402
from models.schemas import PatientBase  # noqa: E402


def _schema_bounds(name):
    """PatientBase 필드의 (ge, le). 없으면 None."""
    field = PatientBase.model_fields.get(name)
    if field is None:
        return None
    ge = le = None
    for meta in field.metadata:
        ge = getattr(meta, "ge", ge)
        le = getattr(meta, "le", le)
    if ge is None and le is None:
        return None
    return (ge, le)


class ClinicalRangesSyncTest(unittest.TestCase):
    def test_ranges_match_schema(self):
        mismatches = []
        for name, (lo, hi) in CLINICAL_RANGES.items():
            bounds = _schema_bounds(name)
            if bounds is None:
                continue  # 스키마에 범위 제약이 없는 필드(이진 플래그 등)는 제외
            ge, le = bounds
            if (float(ge), float(le)) != (float(lo), float(hi)):
                mismatches.append(
                    f"{name}: CLINICAL_RANGES=({lo},{hi}) != schema=({ge},{le})"
                )
        self.assertEqual(
            mismatches, [],
            "CLINICAL_RANGES 와 PatientBase Field 제약이 어긋납니다 "
            "(둘 다 같은 값으로 맞추세요):\n  " + "\n  ".join(mismatches),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
