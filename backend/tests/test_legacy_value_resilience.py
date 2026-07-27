"""레거시 이상값이 있어도 조회가 500 나지 않아야 한다.

실제 병원 장애: 환자 상세를 열면 "환자 데이터를 불러올 수 없습니다" (Dashboard 의
errorKind='unknown' 분기 = 서버가 500 응답). 원인은 구버전(≤v2.3.2) CSV 업로드가
Pydantic 을 거치지 않아 Integer 컬럼에 소수(age=60.7, dm_med_count=2.5)나 범위밖 값
(dm_med_count=31)이 저장됐고, PatientResponse.model_validate 가 ValidationError 를
던져 상세·목록이 통째로 깨진 것.

방어는 2중이다:
  1) PatientResponse 가 정수 컬럼을 float 로 받아 어떤 저장값이든 통과 (이 테스트)
  2) 기동 시 마이그레이션(user_version 236)이 저장값 자체를 정상화 (database.py)

실행: PYTHONPATH=backend python backend/tests/test_legacy_value_resilience.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.schemas import PatientResponse  # noqa: E402

# 구버전이 실제로 저장할 수 있었던 값들 (필드, 값, 설명)
LEGACY_VALUES = [
    ("age", 60.7, "정수 컬럼에 소수"),
    ("dm_med_count", 2.5, "정수 컬럼에 소수"),
    ("dm_med_count", 31, "스키마 상한(30) 초과"),
    ("drinking", 2.5, "정수 컬럼에 소수"),
    ("exercise", 5, "이진 가정 초과(0~3 코드)"),
    ("dm_medication", 0.5, "이진 플래그에 중간값"),
    ("insulin_medication", 2, "이진 플래그 범위밖"),
    ("hypertension", 7, "이진 플래그 범위밖"),
    ("smoking", 0.5, "이진 플래그에 중간값"),
    ("dm_diagnosis_age", 45.5, "정수 컬럼에 소수"),
    ("dm_duration", 12.3, "정수 컬럼에 소수"),
    ("urine_nit", 0.5, "이진 플래그에 중간값"),
    # 이미 v2.2.8/v2.2.9 에서 완화된 것들 — 회귀 방지용으로 함께 고정
    ("hba1c", 0.0, "생리범위 하한 미만"),
    ("fbg", 5, "생리범위 하한 미만"),
    ("sbp", 20, "생리범위 하한 미만"),
    ("height", 40, "생리범위 하한 미만"),
    ("c_peptide", 0.0, "실측 불가값"),
    ("sex", "남성", "비정규 성별 표기"),
]

BASE = {"id": 1, "name": "테스트", "chart_no": "T-1"}


class LegacyValueResilienceTest(unittest.TestCase):
    def test_response_accepts_legacy_values(self):
        """어떤 레거시 값이 있어도 응답 직렬화가 실패하면 안 된다(=상세/목록 500 금지)."""
        broken = []
        for field, value, desc in LEGACY_VALUES:
            try:
                PatientResponse.model_validate({**BASE, field: value})
            except Exception as e:
                broken.append(f"{field}={value!r} ({desc}) → {type(e).__name__}")
        self.assertEqual(
            broken, [],
            "레거시 값에서 응답 검증이 실패했습니다. 해당 필드를 PatientResponse 에서 "
            "완화(Optional[float] 등)하세요. 실패 목록:\n  " + "\n  ".join(broken),
        )

    def test_all_int_columns_are_relaxed_in_response(self):
        """Patient 의 Integer 컬럼은 전부 응답에서 소수를 허용해야 한다."""
        from models.database import Patient
        from sqlalchemy import Integer

        int_cols = [
            c.name for c in Patient.__table__.columns
            if isinstance(c.type, Integer) and c.name != "id"
        ]
        broken = []
        for col in int_cols:
            if col not in PatientResponse.model_fields:
                continue
            try:
                PatientResponse.model_validate({**BASE, col: 1.5})
            except Exception:
                broken.append(col)
        self.assertEqual(
            broken, [],
            f"Integer 컬럼 {broken} 이 응답에서 소수를 거부합니다 → 구버전 데이터로 500 발생 가능",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
