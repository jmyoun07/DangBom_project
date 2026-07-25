"""방문 마스터 필드 정의 ↔ ORM 컬럼 / 업로드 경로 동기화 강제.

v2.3.3 에서 `dm_med_count` 가 `_LATEST_VISIT_MASTER_FIELDS` 에 추가됐지만
`MeasurementHistory` 에는 컬럼이 없어 POST /api/v1/patients 가
`TypeError: 'dm_med_count' is an invalid keyword argument` → 500 으로 전량 실패했다.
(`MeasurementHistory(**core)` 로 전달되므로 목록에 있는 필드는 반드시 컬럼이어야 한다.)

이 테스트는 그 계약을 고정한다:
  1. 모든 방문 마스터 필드는 MeasurementHistory 실제 컬럼이다.
  2. 모든 방문 마스터 필드는 Patient 실제 컬럼이다 (마스터 동기화 대상).
  3. 모든 방문 마스터 필드는 SNAPSHOT_FIELDS 에 포함된다 (컬럼 NULL 시 snapshot fallback).
  4. 업로드의 _TRACKED_VISIT_FIELDS 와 정의가 일치한다.

실행: PYTHONPATH=backend python backend/tests/test_visit_master_fields_sync.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.database import MeasurementHistory, Patient  # noqa: E402
from routers.patients import _LATEST_VISIT_MASTER_FIELDS  # noqa: E402
from routers.upload import _TRACKED_VISIT_FIELDS  # noqa: E402
from services.derived import SNAPSHOT_FIELDS  # noqa: E402


class VisitMasterFieldsSyncTest(unittest.TestCase):
    def test_fields_are_measurement_history_columns(self):
        cols = {c.name for c in MeasurementHistory.__table__.columns}
        missing = [f for f in _LATEST_VISIT_MASTER_FIELDS if f not in cols]
        self.assertEqual(
            missing, [],
            "MeasurementHistory 컬럼 누락 → MeasurementHistory(**core) 가 TypeError(500) 로 실패한다: "
            f"{missing}",
        )

    def test_fields_are_patient_columns(self):
        cols = {c.name for c in Patient.__table__.columns}
        missing = [f for f in _LATEST_VISIT_MASTER_FIELDS if f not in cols]
        self.assertEqual(missing, [], f"Patient 컬럼 누락 (마스터 동기화 불가): {missing}")

    def test_fields_are_snapshot_fields(self):
        missing = [f for f in _LATEST_VISIT_MASTER_FIELDS if f not in SNAPSHOT_FIELDS]
        self.assertEqual(missing, [], f"SNAPSHOT_FIELDS 누락 (컬럼 NULL 시 복원 불가): {missing}")

    def test_upload_tracked_fields_match(self):
        self.assertEqual(
            tuple(_TRACKED_VISIT_FIELDS), tuple(_LATEST_VISIT_MASTER_FIELDS),
            "업로드가 방문 행에 담는 값과 마스터 동기화가 읽는 값이 어긋난다.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
