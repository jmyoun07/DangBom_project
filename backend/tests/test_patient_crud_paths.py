"""수기 환자 등록/수정(POST·PATCH) 전 경로 회귀 테스트.

v2.3.3 회귀: _LATEST_VISIT_MASTER_FIELDS 에 MeasurementHistory 에 없는 필드
(dm_med_count)를 추가하자 MeasurementHistory(**core) 생성자가 TypeError 를 내며
수기 등록·수정이 전부 500 이 됐다. CSV 업로드만 테스트해 잡지 못했다.

이 테스트는 실제 ASGI 앱에 요청을 보내 다음을 보장한다:
  1) POST /patients (수기 등록) 200
  2) PATCH /patients/{id} (수정) 200 — 방문 컬럼·마스터 전용 필드 동시 변경 포함
  3) GET /patients/{id} 200 (응답 스키마 검증 통과)
  4) 방문 snapshot 에 간수치 등 전체 검사값이 보존되는지
  5) MeasurementHistory 생성자에 실제 컬럼만 전달되는지 (상수 오염 방지)

실행: PYTHONPATH=backend python backend/tests/test_patient_crud_paths.py
"""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import models.database as mdb  # noqa: E402

_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
_ENGINE = create_engine(f"sqlite:///{_TMP.name}", connect_args={"check_same_thread": False})
mdb.engine = _ENGINE
mdb.SessionLocal = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)
mdb.Base.metadata.create_all(bind=_ENGINE)

import main  # noqa: E402
from models.database import MeasurementHistory  # noqa: E402
from routers.patients import _LATEST_VISIT_MASTER_FIELDS  # noqa: E402

mdb.SessionLocal = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


async def _call(method, path, body=None):
    headers = [(b"host", b"test")]
    if body:
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "scheme": "http",
        "server": ("test", 80), "client": ("test", 1), "headers": headers,
    }
    out = {"status": None, "body": b""}

    async def receive():
        return {"type": "http.request", "body": body or b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    await main.app(scope, receive, send)
    return out


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


PATIENT = {
    "name": "테스트환자", "chart_no": "TST-0001", "dob": "1968-03-10", "sex": "F",
    "phone": "010-0000-0000", "exam_date": "2026-07-25",
    "height": 157.2, "weight": 43.4, "sbp": 96, "dbp": 67,
    "hba1c": 6.0, "fbg": 99, "c_peptide": 1.08,
    "total_cholesterol": 103, "triglycerides": 91, "hdl": 42, "ldl": 42,
    "cr": 0.64, "ast": 34, "alt": 47, "ggt": 10,
}


class PatientCrudPathsTest(unittest.TestCase):
    def test_visit_fields_are_real_columns(self):
        """방문 생성자에 쓰이는 필드는 measurement_history 실제 컬럼이어야 한다.

        v2.3.3 회귀: _LATEST_VISIT_MASTER_FIELDS 에 컬럼 없는 필드(dm_med_count)를
        넣자 MeasurementHistory(**core) 가 TypeError → 수기 등록/수정 전부 500.
        구현 방식(컬럼 추가 / 상수 분리)과 무관하게, 생성자에 넘어가는 필드가
        실제 컬럼인지를 직접 검증한다.
        """
        cols = {c["name"] for c in inspect(_ENGINE).get_columns("measurement_history")}
        for field in _LATEST_VISIT_MASTER_FIELDS:
            self.assertIn(
                field, cols,
                f"'{field}' 가 measurement_history 컬럼에 없습니다. "
                "MeasurementHistory 생성자에 전달되면 TypeError → 등록/수정 500 이 됩니다. "
                "컬럼을 추가하거나, 생성자에 넘기는 필드 목록에서 제외하세요.",
            )

    def test_create_patch_get_predict(self):
        r = _run(_call("POST", "/api/v1/patients", json.dumps(PATIENT).encode()))
        self.assertEqual(r["status"], 200, f"수기 등록 실패: {r['body'][:300]}")
        pid = json.loads(r["body"])["data"]["id"]

        # 방문 snapshot 에 간수치가 보존되는가 (통합리포트 간수치 그래프의 소스)
        session = mdb.SessionLocal()
        visits = session.query(MeasurementHistory).filter(
            MeasurementHistory.patient_id == pid
        ).all()
        self.assertTrue(visits, "방문 이력이 생성되지 않았습니다")
        snap = json.loads(visits[0].snapshot or "{}")
        for key, expected in (("alt", 47), ("ast", 34), ("ggt", 10)):
            self.assertEqual(snap.get(key), expected, f"snapshot 에 {key} 미보존")
        session.close()

        # 방문 컬럼(hba1c) + 마스터 전용 필드(dm_med_count) 동시 수정
        r = _run(_call("PATCH", f"/api/v1/patients/{pid}",
                       json.dumps({"hba1c": 7.1, "dm_med_count": 3, "alt": 50}).encode()))
        self.assertEqual(r["status"], 200, f"환자 수정 실패: {r['body'][:300]}")

        r = _run(_call("GET", f"/api/v1/patients/{pid}"))
        self.assertEqual(r["status"], 200, f"환자 조회 실패: {r['body'][:300]}")
        detail = json.loads(r["body"])["data"]["patient"]
        self.assertEqual(detail.get("hba1c"), 7.1)
        self.assertEqual(detail.get("dm_med_count"), 3)

        r = _run(_call("POST", "/api/v1/predict", json.dumps({"patient_id": pid}).encode()))
        self.assertEqual(r["status"], 200, f"예측 실패: {r['body'][:300]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
