"""
환자 데이터 CSV 미러.
- SQL DB (%APPDATA%\\DB-care\\dbcare.db) 는 그대로 유지하고,
  사용자가 Excel 로 직접 볼 수 있도록 %APPDATA%\\DB-care\\export\\ 에 CSV 를 미러 한다.
- 환자 등록 / 수정 / CSV 업로드 / 측정 이력 추가 모든 쓰기 시점에서
  BackgroundTasks 로 비동기 호출 → 사용자 응답 지연 0.

폴더 구조:
  export\\
    ├── 환자_전체.csv                                ← 전체 환자 메타 (한 파일)
    ├── YYYY\\MM\\<이름>_<차트번호>.csv              ← 검사일 기준 시점 스냅샷
    └── 환자별\\<이름>_<차트번호>\\
            ├── 정보.csv
            └── 검사_이력.csv                        ← 시계열 누적
"""
from __future__ import annotations

import csv
import os
import re
import sys
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models.database import Patient, MeasurementHistory

logger = logging.getLogger(__name__)


# ── 경로 결정 ────────────────────────────────────────────────

def _export_root() -> Path:
    """
    CSV 미러 폴더 위치 — DB 파일 폴더와 동일 (APPDATA\\DB-care\\export).
    환경변수 DBCARE_EXPORT_PATH 로 override 가능.
    """
    override = os.environ.get("DBCARE_EXPORT_PATH")
    if override:
        p = Path(override).expanduser().resolve()
    else:
        is_frozen = getattr(sys, "frozen", False)
        is_desktop = os.environ.get("DBCARE_DESKTOP") == "1"
        if is_frozen or is_desktop:
            if sys.platform == "win32":
                base = Path(os.environ.get("APPDATA", str(Path.home()))) / "DB-care"
            elif sys.platform == "darwin":
                base = Path.home() / "Library" / "Application Support" / "DB-care"
            else:
                base = Path.home() / ".dbcare"
        else:
            base = Path(__file__).resolve().parent.parent  # backend/
        p = base / "export"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── 파일명 안전화 (Windows 금지 문자 제거) ───────────────────────

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(s: str) -> str:
    """Windows 파일명에 허용되지 않는 문자를 _ 로. 빈 문자열은 'unknown'."""
    if not s:
        return "unknown"
    clean = _FORBIDDEN.sub("_", str(s)).strip().rstrip(". ")
    return clean or "unknown"


def _patient_folder_name(p: Patient) -> str:
    """'<이름>_<차트번호>' 형식."""
    return f"{_safe_filename(p.name or '환자')}_{_safe_filename(p.chart_no or 'no-chart')}"


# ── 컬럼 정의 (한글 헤더) ─────────────────────────────────────

# 환자 메타 컬럼 — 사용자가 Excel 에서 봤을 때 헷갈리지 않도록 한글.
PATIENT_COLS: list[tuple[str, str]] = [
    ("name",               "이름"),
    ("chart_no",           "차트번호"),
    ("dob",                "생년월일"),
    ("sex",                "성별"),
    ("age",                "나이"),
    ("phone",              "연락처"),
    ("exam_date",          "검사일"),
    ("upload_date",        "등록일"),
    ("risk_level",         "종합위험도"),
    # 혈당
    ("hba1c",              "당화혈색소(HbA1c, %)"),
    ("fbg",                "공복혈당(mg/dL)"),
    ("c_peptide",          "C-peptide(ng/mL)"),
    # 신체
    ("height",             "키(cm)"),
    ("weight",             "몸무게(kg)"),
    ("bmi",                "BMI(kg/m²)"),
    ("sbp",                "수축기혈압(mmHg)"),
    ("dbp",                "이완기혈압(mmHg)"),
    ("pulse_pressure",     "맥압(mmHg)"),
    # 지질
    ("total_cholesterol",  "총콜레스테롤(mg/dL)"),
    ("triglycerides",      "중성지방(mg/dL)"),
    ("hdl",                "HDL(mg/dL)"),
    ("ldl",                "LDL(mg/dL)"),
    ("ldl_calc",           "LDL_계산값(Friedewald)"),
    ("non_hdl",            "non-HDL(mg/dL)"),
    # 신장 / 간
    ("cr",                 "크레아티닌(mg/dL)"),
    ("egfr",               "eGFR(mL/min/1.73m²)"),
    ("ast",                "AST(U/L)"),
    ("alt",                "ALT(U/L)"),
    ("ggt",                "GGT(U/L)"),
    # 인슐린 저항성 파생
    ("homa_ir",            "HOMA-IR"),
    ("homa_beta",          "HOMA-beta"),
    ("tyg_index",          "TyG index"),
    ("bmi_homa_ir",        "BMI×HOMA-IR"),
    # 당뇨
    ("dm_diagnosis_age",   "당뇨진단나이(세)"),
    ("dm_duration",        "당뇨이환기간(년)"),
    ("dm_medication",      "당뇨약 복용(0/1)"),
    ("insulin_medication", "인슐린 사용(0/1)"),
    # 과거력/생활습관
    ("hypertension",       "고혈압 진단(0/1)"),
    ("smoking",            "흡연(0/1)"),
    ("drinking",           "음주(0/1)"),
    ("exercise",           "운동(0/1)"),
    ("sleep_hours",        "수면시간(시간)"),
    # 소변 dipstick
    ("he_upro",            "단백뇨"),
    ("he_uglu",            "요당"),
    ("he_ubld",            "요잠혈"),
    ("urine_bil",          "빌리루빈"),
    ("urine_uro",          "우로빌리노겐"),
    ("urine_ket",          "케톤"),
    ("urine_nit",          "아질산염"),
    ("urine_ph",           "요pH"),
    ("urine_sg",           "요비중"),
]

# 측정 이력 컬럼
MEAS_COLS: list[tuple[str, str]] = [
    ("measured_at", "측정일"),
    ("hba1c",       "당화혈색소(HbA1c, %)"),
    ("c_peptide",   "C-peptide(ng/mL)"),
    ("cr",          "크레아티닌(mg/dL)"),
]


def _sanitize_cell(s: str) -> str:
    """v2.1.9 (감사): CSV/Excel formula injection 방어.
    =,+,-,@,탭,CR 로 시작하는 셀은 ' 를 붙여 Excel 수식 실행 차단."""
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def _val(obj, key: str) -> str:
    """ORM 객체의 값을 CSV 셀 문자열로. None → 빈칸, date/datetime → ISO 문자열."""
    v = getattr(obj, key, None)
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return _sanitize_cell(str(v))


# ── 단일 환자 export ─────────────────────────────────────────

def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """UTF-8 BOM 포함 (Excel 한글 깨짐 방지)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def export_patient(db: Session, patient_id: int) -> None:
    """
    한 환자의 CSV 미러를 갱신한다.
      - 환자별\\<이름>_<차트번호>\\정보.csv   (1행, 최신 메타)
      - 환자별\\<이름>_<차트번호>\\검사_이력.csv (N행, 시계열)
      - YYYY\\MM\\<이름>_<차트번호>.csv      (검사일 기준 스냅샷, 1행)
    """
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        return
    try:
        root = _export_root()
        folder = _patient_folder_name(p)

        header = [label for (_, label) in PATIENT_COLS]
        row = [_val(p, key) for (key, _) in PATIENT_COLS]

        # 1) 환자별\\<폴더>\\정보.csv
        per_patient_dir = root / "환자별" / folder
        _write_csv(per_patient_dir / "정보.csv", header, [row])

        # 2) 환자별\\<폴더>\\검사_이력.csv (시계열, 측정일 오름차순)
        meas_rows = (
            db.query(MeasurementHistory)
            .filter(MeasurementHistory.patient_id == p.id)
            .order_by(MeasurementHistory.measured_at.asc())
            .all()
        )
        meas_header = [label for (_, label) in MEAS_COLS]
        meas_data = [[_val(m, k) for (k, _) in MEAS_COLS] for m in meas_rows]
        _write_csv(per_patient_dir / "검사_이력.csv", meas_header, meas_data)

        # 3) YYYY\\MM\\<이름>_<차트번호>.csv — 검사일 기준 스냅샷
        snapshot_date: Optional[date] = p.exam_date
        if snapshot_date is None and p.upload_date is not None:
            snapshot_date = p.upload_date.date()
        if snapshot_date is None:
            snapshot_date = date.today()

        year_dir = root / f"{snapshot_date.year:04d}" / f"{snapshot_date.month:02d}"
        _write_csv(year_dir / f"{folder}.csv", header, [row])

    except Exception as e:
        # CSV 미러 실패가 본 API 응답을 깨면 안 되므로 로그만.
        logger.warning(f"export_patient({patient_id}) 실패: {e}")


# ── 전체 환자 일괄 export ────────────────────────────────────

def export_all_patients(db: Session) -> dict:
    """
    모든 환자 + 환자_전체.csv 일괄 갱신. Settings 의 "전체 다시 내보내기" 버튼용.
    반환: 처리 건수.
    """
    root = _export_root()
    patients = db.query(Patient).order_by(Patient.id.asc()).all()

    # 환자별 / 연월별 — 한 명씩
    for p in patients:
        export_patient(db, p.id)

    # 환자_전체.csv — 모든 환자 한 파일
    try:
        header = [label for (_, label) in PATIENT_COLS]
        rows = [[_val(p, key) for (key, _) in PATIENT_COLS] for p in patients]
        _write_csv(root / "환자_전체.csv", header, rows)
    except Exception as e:
        logger.warning(f"환자_전체.csv 쓰기 실패: {e}")

    return {"patients": len(patients), "root": str(root)}


def get_export_root() -> Path:
    """외부에서 폴더 경로만 알고 싶을 때."""
    return _export_root()
