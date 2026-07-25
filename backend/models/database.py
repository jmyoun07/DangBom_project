"""
DB-care Database Models + Seed Data
"""
from __future__ import annotations
import os
import sys
import random
from pathlib import Path
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session


def _resolve_db_path() -> Path:
    """
    DB 파일 경로 결정.
    - 패키지 모드 (PyInstaller 빌드된 exe) → %APPDATA%/DB-care/dbcare.db
      사용자별 데이터 분리 + 업데이트 시 DB 유지.
    - 개발 모드 → backend/dbcare.db (기존 위치 유지)
    환경변수 DBCARE_DB_PATH 가 있으면 그 값을 우선 사용.
    """
    override = os.environ.get("DBCARE_DB_PATH")
    if override:
        p = Path(override).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    is_frozen = getattr(sys, "frozen", False)
    is_desktop = os.environ.get("DBCARE_DESKTOP") == "1"

    if is_frozen or is_desktop:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", str(Path.home()))) / "DB-care"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "DB-care"
        else:
            base = Path.home() / ".dbcare"
        base.mkdir(parents=True, exist_ok=True)
        return base / "dbcare.db"

    # 개발 모드 — backend 폴더 안 (기존 위치)
    return Path(__file__).resolve().parent.parent / "dbcare.db"


DB_FILE = _resolve_db_path()
DATABASE_URL = f"sqlite:///{DB_FILE.as_posix()}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_lightweight_migrations() -> None:
    """
    SQLite 자동 마이그레이션 — ORM 모델에 새 컬럼이 추가됐을 때
    기존 DB 파일에도 ADD COLUMN 으로 반영한다.
    Base.metadata.create_all 은 테이블이 이미 있으면 새 컬럼을 추가해 주지 않음.
    """
    from sqlalchemy import text, inspect
    try:
        inspector = inspect(engine)
        if not inspector.has_table("patients"):
            return  # 첫 실행: create_all 이 처리함

        existing_cols = {c["name"] for c in inspector.get_columns("patients")}

        # v2.1.8 — 마이그레이션(ALTER/UPDATE) 전 1회성 백업.
        # 실제 환자 DB 파일이 있을 때만, 아직 백업이 없으면 .bak 생성.
        try:
            if DB_FILE.exists() and DB_FILE.stat().st_size > 0:
                bak = DB_FILE.with_suffix(DB_FILE.suffix + ".premigrate.bak")
                if not bak.exists():
                    import shutil
                    shutil.copy2(DB_FILE, bak)
                    print(f"[MIGRATION] DB 백업 생성: {bak}")
        except Exception as _bak_err:
            print(f"[MIGRATION] DB 백업 실패 (계속 진행): {_bak_err}")
        # 새 컬럼들 (향후 추가 시 여기에 나열)
        needed = {
            "risk_level":         "VARCHAR",
            # v2 통일 스키마 (병원 수집 항목 반영)
            "urine_bil":          "FLOAT",
            "urine_uro":          "FLOAT",
            "urine_ket":          "FLOAT",
            "urine_nit":          "INTEGER",
            "urine_ph":           "FLOAT",
            "urine_sg":           "FLOAT",
            "sleep_hours":        "FLOAT",
            "dm_medication":      "INTEGER",
            "dm_med_count":       "INTEGER",   # v2.3.3 병원 핵심 요청(당뇨약 개수)
            "insulin_medication": "INTEGER",
            "visceral_fat":       "FLOAT",
            # ── 파생 변수 컬럼 ──
            "egfr":               "FLOAT",
            "ldl_calc":           "FLOAT",
            "non_hdl":            "FLOAT",
            "homa_ir":            "FLOAT",
            "homa_beta":          "FLOAT",
            "tyg_index":          "FLOAT",
            "bmi_homa_ir":        "FLOAT",
            "pulse_pressure":     "FLOAT",
        }
        missing = {k: v for k, v in needed.items() if k not in existing_cols}
        if missing:
            with engine.begin() as conn:
                for col, sqltype in missing.items():
                    conn.execute(text(f"ALTER TABLE patients ADD COLUMN {col} {sqltype}"))
                    print(f"[MIGRATION] patients.{col} ({sqltype}) 추가됨")

        # ── 항목6: measurement_history.bmi 추가 (BMI 추이 차트용) ──
        #   과거 측정에는 BMI 실측이 없으므로 backfill 하지 않고 NULL 유지(가짜 flat 추이 방지).
        #   신규 업로드/수기 등록분부터 실제 BMI 가 기록된다. (codex+리뷰 검수 반영)
        if inspector.has_table("measurement_history"):
            mh_cols = {c["name"] for c in inspector.get_columns("measurement_history")}
            if "bmi" not in mh_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE measurement_history ADD COLUMN bmi FLOAT"))
                    print("[MIGRATION] measurement_history.bmi 추가 (과거행 NULL 유지)")
            # v2.2.9: 방문별 전체 검사값 JSON (검사이력 페이지 — 방문별 전체 패널/위험도 산출용)
            if "snapshot" not in mh_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE measurement_history ADD COLUMN snapshot TEXT"))
                    print("[MIGRATION] measurement_history.snapshot 추가 (과거행 NULL — 백필로 최신 방문 채움)")
            # v2.3.4: 당뇨약 개수 방문 추적 (v2.3.3 에서 컬럼 없이 쓰여 등록 500 발생)
            if "dm_med_count" not in mh_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE measurement_history ADD COLUMN dm_med_count INTEGER"))
                    print("[MIGRATION] measurement_history.dm_med_count 추가 (과거행 NULL 유지)")

        # ── 졸업자 데이터 보강 컬럼 (병원 6/13: C-peptide·eGFR·합병증 전/후) ──
        if inspector.has_table("graduates"):
            g_cols = {c["name"] for c in inspector.get_columns("graduates")}
            g_needed = {
                "egfr": "FLOAT", "cpep_before": "FLOAT", "cpep_after": "FLOAT",
                "egfr_before": "FLOAT", "egfr_after": "FLOAT",
                "comp_before": "VARCHAR", "comp_after": "VARCHAR",
            }
            g_missing = {k: v for k, v in g_needed.items() if k not in g_cols}
            if g_missing:
                with engine.begin() as conn:
                    for col, sqltype in g_missing.items():
                        conn.execute(text(f"ALTER TABLE graduates ADD COLUMN {col} {sqltype}"))
                print(f"[MIGRATION] graduates 컬럼 추가: {list(g_missing)}")

        # patient_audit 테이블 생성 (N2)
        # — Base.metadata.create_all 이 새 테이블을 자동 생성하지만,
        #   기존 DB 에 명시적으로 보장하기 위해 한 번 더 호출.
        Base.metadata.create_all(bind=engine, tables=[PatientAudit.__table__])

        # ── v2.1.3 마이그레이션 ── user_version pragma 로 한 번만 실행 보장
        # 213 미만 → risk_level 일괄 NULL 화 (새 안전망 룰 + 모델 threshold + C-펩 양면성 반영용).
        # 다음 환자 목록/상세 조회 시 _ensure_risk_level / BackgroundTask 가 자동 재계산.
        try:
            with engine.begin() as conn:
                cur_ver = conn.execute(text("PRAGMA user_version")).scalar() or 0
                if cur_ver < 213:
                    cleared = conn.execute(text(
                        "UPDATE patients SET risk_level = NULL WHERE risk_level IS NOT NULL"
                    )).rowcount
                    if cleared:
                        print(f"[MIGRATION v2.1.3] risk_level {cleared}건 무효화 (다음 조회 시 새 로직으로 재계산)")
                    conn.execute(text("PRAGMA user_version = 213"))
                    print("[MIGRATION] user_version → 213")
        except Exception as e:
            print(f"[MIGRATION v2.1.3] risk_level 무효화 실패: {e}")

        # ── v2.1.3 — measurement_history (patient_id, measured_at) unique index ──
        # 기존 DB 에 unique constraint 없을 경우 추가. 중복이 있다면 가장 최근 1건만 보존.
        try:
            with engine.begin() as conn:
                # 중복 제거 — 같은 (patient_id, measured_at) 의 가장 오래된 id 만 남김
                dup_removed = conn.execute(text("""
                    DELETE FROM measurement_history
                    WHERE id NOT IN (
                        SELECT MIN(id) FROM measurement_history
                        GROUP BY patient_id, measured_at
                    )
                """)).rowcount
                if dup_removed:
                    print(f"[MIGRATION] 중복 measurement_history {dup_removed}건 정리")
                # SQLite 는 CREATE UNIQUE INDEX IF NOT EXISTS 지원
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_measurement_patient_date "
                    "ON measurement_history (patient_id, measured_at)"
                ))
        except Exception as e:
            print(f"[MIGRATION] measurement_history unique index 적용 실패: {e}")

        # ── 고아 레코드 정리 (BUGFIX v2.0.4) ──
        # 이전 버전 clear_patients() 가 bulk delete 만 호출해서
        # measurement_history / patient_audit 가 patients 없이 남아 있었음.
        # SQLite 가 환자 id 를 재사용 → 새 환자가 옛 측정이력을 물려받는 버그.
        # 앱 시작 시 한번 청소.
        with engine.begin() as conn:
            mh_orphans = conn.execute(text(
                "DELETE FROM measurement_history "
                "WHERE patient_id NOT IN (SELECT id FROM patients)"
            )).rowcount
            if mh_orphans:
                print(f"[MIGRATION] 고아 measurement_history {mh_orphans}건 정리")
            # patient_audit 도 동일 처리 (기존 ondelete=CASCADE 가 있어 보통 비어있지만 방어적)
            if inspector.has_table("patient_audit"):
                pa_orphans = conn.execute(text(
                    "DELETE FROM patient_audit "
                    "WHERE patient_id NOT IN (SELECT id FROM patients)"
                )).rowcount
                if pa_orphans:
                    print(f"[MIGRATION] 고아 patient_audit {pa_orphans}건 정리")
    except Exception as e:
        print(f"[MIGRATION] 자동 마이그레이션 실패: {e}")


# ── ORM Models ────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    chart_no = Column(String, unique=True, nullable=False)
    dob = Column(Date)
    sex = Column(String)          # "M" / "F"
    age = Column(Integer)
    phone = Column(String)

    # 혈당 지표
    hba1c = Column(Float)
    c_peptide = Column(Float)
    fbg = Column(Float)           # 공복혈당 (HE_glu)
    he_insulin = Column(Float)    # 인슐린

    # 간 기능
    ggt = Column(Float)
    alt = Column(Float)
    ast = Column(Float)

    # 신장 기능
    cr = Column(Float)            # 크레아티닌 (HE_crea)  — eGFR 자동 파생

    # 지질
    total_cholesterol = Column(Float)
    triglycerides = Column(Float)
    hdl = Column(Float)
    ldl = Column(Float)           # 실측. 없으면 LDL_calc 파생

    # 혈압 / 신체
    sbp = Column(Float)
    dbp = Column(Float)
    bmi = Column(Float)
    height = Column(Float)        # HE_ht
    weight = Column(Float)        # HE_wt

    # (v2 제거됨 — 병원 미수집: bun, he_ualb, he_ucrea, waist, hemoglobin, wbc, rbc)
    # ORM 컬럼 자체는 남겨두지 않음. 기존 DB 에는 남아있을 수 있지만
    # Pydantic 스키마에서 노출 안 되므로 API 로는 read/write 불가.

    # 소변 dipstick (KNHANES 코드: 1=음성, ≥2=양성. predictor._urine_pos threshold=2)
    #   v2.2.7: 입력 폼(ManualPatientForm/EditPatientModal) 모두 1~6 로 통일됨.
    he_upro = Column(Float)
    he_uglu = Column(Float)
    he_ubld = Column(Float)
    # 소변 확장 (병원 dipstick 전체 — 재학습 v2 모델 사용)
    urine_bil = Column(Float)       # BIL (빌리루빈)      1=음성 ~ 5 (≥2 양성)
    urine_uro = Column(Float)       # URO (유로빌리노겐)  1=음성 ~ 5 (≥2 비정상)
    urine_ket = Column(Float)       # KET (케톤)         1=음성 ~ 5 (≥2 양성)
    urine_nit = Column(Integer)     # NIT (아질산염)     0/1
    urine_ph = Column(Float)        # pH
    urine_sg = Column(Float)        # 요비중 (1.005~1.030)

    # 과거력 / 생활습관 (0/1, 미상=NULL)
    # v2.3.0 (감사): default=0 은 '측정 안 함'을 '없음'으로 단정해 모델의 결측 처리
    #   (KNNImputer)를 무력화했다 → NULL 허용. 기존 행의 0 값은 그대로 유지된다.
    hypertension = Column(Integer)
    smoking = Column(Integer)
    drinking = Column(Integer)
    exercise = Column(Integer)
    sleep_hours = Column(Float)          # 하루 평균 수면시간(시간) — >=7 이면 sleep_7h=1

    # 당뇨 관련
    dm_diagnosis_age = Column(Integer)
    dm_duration = Column(Integer)
    dm_medication = Column(Integer)         # 당뇨약 복용 여부 (미상=NULL, v2.3.0)
    dm_med_count = Column(Integer)          # 당뇨약 개수 (병원 핵심 요청, v2.3.3) — 모델 미사용, 표시/시나리오용
    insulin_medication = Column(Integer)    # 인슐린 투약 여부 (미상=NULL, v2.3.0)

    # 기타 (모델에는 포함 안 되지만 병원에서 수집)
    visceral_fat = Column(Float)     # 내장지방 레벨

    # ── 파생 변수 (백엔드가 원본값으로 자동 계산해 저장) ──
    # 업로드·편집 시 _compute_derived_fields() 호출로 갱신됨.
    # DB 에 저장해 두면 ① 쿼리/정렬 가능 ② CSV export 시 완전한 스냅샷
    egfr = Column(Float)                # CKD-EPI 공식 — 신장 기능 (mL/min/1.73m²)
    ldl_calc = Column(Float)            # Friedewald: chol - HDL - TG/5
    non_hdl = Column(Float)             # chol - HDL
    homa_ir = Column(Float)             # glu × insulin / 405
    homa_beta = Column(Float)           # 360 × insulin / (glu - 63)
    tyg_index = Column(Float)           # ln(TG × glu / 2)
    bmi_homa_ir = Column(Float)         # BMI × HOMA_IR
    pulse_pressure = Column(Float)      # SBP - DBP

    upload_date = Column(DateTime, default=datetime.utcnow)
    exam_date = Column(Date)  # 최근 검사일 (CSV에서 받음)

    # 사전 계산된 최고 위험도 — "고위험" | "중위험" | "저위험"
    # CSV 업로드 / POST / PATCH 시 ML 예측으로 계산해 저장한다.
    # 환자 목록 조회 시 ML 재실행 없이 이 컬럼만 읽어 즉시 반환 (성능 최적화).
    risk_level = Column(String, nullable=True)

    # 관계
    measurements = relationship("MeasurementHistory", back_populates="patient", cascade="all, delete-orphan")


class MeasurementHistory(Base):
    __tablename__ = "measurement_history"
    # v2.1.3 (Codex 리뷰 반영): 동일 환자 + 동일 검사일 측정 중복 차단.
    # 동시 POST race condition 으로 측정 이력 중복 insert 가능했던 버그 방어.
    __table_args__ = (
        UniqueConstraint("patient_id", "measured_at", name="uq_measurement_patient_date"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    measured_at = Column(Date, nullable=False)
    c_peptide = Column(Float)
    hba1c = Column(Float)
    cr = Column(Float)
    bmi = Column(Float)   # 항목6: BMI 추이 차트용 (업로드 시 파생 BMI 저장)
    # v2.3.4: 당뇨약 개수도 방문마다 달라지는 값이라 routers/patients.py 의
    #   _LATEST_VISIT_MASTER_FIELDS 에 포함됐지만 컬럼이 없어 환자 등록이 500 으로 실패했다.
    dm_med_count = Column(Integer)
    snapshot = Column(String)   # v2.2.9: 방문 시점 전체 검사값 JSON (검사이력 페이지 — 전체 패널/방문별 위험도)

    patient = relationship("Patient", back_populates="measurements")


class PatientAudit(Base):
    """
    환자 데이터 변경 이력 (N2 audit trail).
    - PATCH /api/v1/patients/{id} 호출 시 변경된 필드별로 한 행씩 기록.
    - PatientDetail 의 '수정 이력' 카드에서 GET /patients/{id}/audit 로 조회.
    - 환자가 삭제되면 cascade 로 함께 정리된다.
    """
    __tablename__ = "patient_audit"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    field_name = Column(String, nullable=False)
    old_value = Column(String)   # JSON-safe 문자열 (None 가능)
    new_value = Column(String)
    actor = Column(String, default="system")  # 추후 인증 도입 시 사용자 ID


class Graduate(Base):
    """전지점 졸업자 데이터 (유사사례 분석용).
    Settings 에서 엑셀('졸업자 리스트' 시트)을 업로드하면 services/graduates.py 가
    파싱해 이 테이블을 통째로 교체한다. 합병증 위험점수 전/후·C-peptide·GFR 은
    원본 엑셀에 없어 추후 데이터 보강 시 연결한다(현재 None)."""
    __tablename__ = "graduates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    chart_no = Column(String, index=True)
    name = Column(String)
    sex = Column(String)                  # 'M' / 'F'
    age = Column(Integer)                 # 결제일 기준 나이
    treatment_months = Column(Integer)    # 한약복용기간(개월) = 치료기간
    dm_duration_months = Column(Integer)  # 유병기간(개월차)
    init_bmi = Column(Float)              # 초진 BMI
    dm_med_count = Column(Float)          # 당뇨약 개수 (숫자만, 아니면 None)
    hba1c_before = Column(Float)          # 치료전 HbA1c
    hba1c_after = Column(Float)           # 치료후 HbA1c
    hba1c_drop = Column(Float)            # 감소 차이
    neuro_improve = Column(String)        # 당뇨발저림 호전 정도
    goal = Column(String)                 # 목표 (당뇨초기 / 완치 등)
    # ── 데이터 보강 필드 (병원 6/13 피드백: 졸업자 전/후 데이터) ──
    egfr = Column(Float)                  # 신장기능 (GFR<60 신장 호전 사례용, 단일값 하위호환)
    cpep_before = Column(Float)           # C-peptide 치료전
    cpep_after = Column(Float)            # C-peptide 치료후
    egfr_before = Column(Float)           # eGFR 치료전 (신장 회복 사례용)
    egfr_after = Column(Float)            # eGFR 치료후
    comp_before = Column(String)          # 합병증 위험도 전 (JSON: {neuro,retina,kidney,cardio,cerebro,dementia})
    comp_after = Column(String)           # 합병증 위험도 후 (JSON)


# ── Seed Data ─────────────────────────────────────────────────

SEED_PATIENTS = [
    {"name": "김영호", "sex": "M", "age": 64, "dob": date(1961, 3, 15), "dm_diagnosis_age": 52},
    {"name": "박미경", "sex": "F", "age": 58, "dob": date(1967, 7, 22), "dm_diagnosis_age": 48},
    {"name": "이승철", "sex": "M", "age": 71, "dob": date(1954, 11, 8), "dm_diagnosis_age": 55},
    {"name": "정수연", "sex": "F", "age": 55, "dob": date(1970, 1, 30), "dm_diagnosis_age": 45},
    {"name": "최동우", "sex": "M", "age": 67, "dob": date(1958, 5, 12), "dm_diagnosis_age": 58},
    {"name": "한지영", "sex": "F", "age": 62, "dob": date(1963, 9, 3), "dm_diagnosis_age": 50},
    {"name": "오민석", "sex": "M", "age": 59, "dob": date(1966, 12, 18), "dm_diagnosis_age": 47},
    {"name": "윤서현", "sex": "F", "age": 73, "dob": date(1952, 4, 25), "dm_diagnosis_age": 60},
    {"name": "장태준", "sex": "M", "age": 56, "dob": date(1969, 8, 7), "dm_diagnosis_age": 44},
    {"name": "송미래", "sex": "F", "age": 65, "dob": date(1960, 6, 14), "dm_diagnosis_age": 53},
]


def _rand(low, high, precision=1):
    return round(random.uniform(low, high), precision)


def create_seed_data():
    """앱 시작 시 시드 데이터 10명 + 6개월 측정 이력 생성.
    기본값: OFF (DB 비워서 시작). DBCARE_SEED=1 환경변수로만 활성화."""
    if os.environ.get("DBCARE_SEED", "0") != "1":
        return
    db = SessionLocal()
    try:
        if db.query(Patient).count() > 0:
            return  # 이미 있으면 스킵

        random.seed(42)
        today = date.today()

        for i, seed in enumerate(SEED_PATIENTS):
            chart_no = f"CN-{2024:04d}-{i+1:04d}"
            p = Patient(
                name=seed["name"],
                chart_no=chart_no,
                dob=seed["dob"],
                sex=seed["sex"],
                age=seed["age"],
                phone=f"010-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                hba1c=_rand(6.0, 10.5),
                c_peptide=_rand(0.8, 4.5),
                fbg=_rand(100, 250),
                he_insulin=_rand(3, 25),
                ggt=_rand(15, 120),
                alt=_rand(10, 80),
                ast=_rand(10, 70),
                cr=_rand(0.6, 2.5),
                total_cholesterol=_rand(140, 280),
                triglycerides=_rand(80, 350),
                hdl=_rand(30, 75),
                ldl=_rand(70, 190),
                sbp=_rand(110, 170),
                dbp=_rand(65, 100),
                bmi=_rand(20, 35),
                height=_rand(150, 185),
                weight=_rand(50, 100),
                he_upro=random.choice([1, 1, 1, 2, 3, 4]),       # dipstick 1=음성
                he_uglu=random.choice([1, 1, 1, 2, 3, 4]),
                he_ubld=random.choice([1, 1, 1, 2, 3]),
                urine_bil=random.choice([1, 1, 1, 2]),
                urine_uro=random.choice([1, 1, 1, 2]),
                urine_ket=random.choice([1, 1, 1, 2]),
                urine_nit=random.choice([0, 0, 0, 1]),
                urine_ph=_rand(5.0, 7.5),
                urine_sg=round(random.uniform(1.005, 1.030), 3),
                hypertension=random.choice([0, 0, 1, 1, 1]),
                smoking=random.choice([0, 0, 0, 1]),
                drinking=random.choice([0, 0, 1, 1]),
                exercise=random.choice([0, 1, 1]),
                sleep_hours=_rand(5.0, 9.0),
                dm_diagnosis_age=seed["dm_diagnosis_age"],
                dm_duration=seed["age"] - seed["dm_diagnosis_age"],
                dm_medication=random.choice([0, 1, 1, 1]),
                insulin_medication=random.choice([0, 0, 0, 1]),
                visceral_fat=_rand(4, 15),
                upload_date=datetime.now() - timedelta(days=random.randint(0, 30)),
            )
            db.add(p)
            db.flush()

            # 6개월 측정 이력
            for month_offset in range(6):
                m_date = today - timedelta(days=30 * (5 - month_offset))
                mh = MeasurementHistory(
                    patient_id=p.id,
                    measured_at=m_date,
                    c_peptide=max(0.5, p.c_peptide + _rand(-0.5, 0.5)),
                    hba1c=max(5.0, p.hba1c + _rand(-0.3, 0.3)),
                    cr=max(0.4, p.cr + _rand(-0.2, 0.2)),
                    bmi=max(16.0, (p.bmi or 23.0) + _rand(-1.0, 1.0)),
                )
                db.add(mh)

        db.commit()
        print(f"[SEED] {len(SEED_PATIENTS)}명 환자 + 측정 이력 생성 완료")
    finally:
        db.close()
