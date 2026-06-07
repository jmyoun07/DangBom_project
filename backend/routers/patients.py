"""
환자 CRUD API
"""
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from models.database import get_db, Patient, MeasurementHistory, PatientAudit, SessionLocal
from models.schemas import PatientCreate, PatientResponse, PatientListResponse, MeasurementResponse, PatientUpdate
from ml.predictor import predict_all
from services.derived import compute_derived
from services.export_csv import export_patient as _export_patient_csv, export_all_patients as _export_all_csv

router = APIRouter(prefix="/api/v1", tags=["patients"])


# ── Audit helpers ─────────────────────────────────────────────

# 감사 대상에서 제외하는 필드 (자동 파생 / 메타데이터)
_AUDIT_EXCLUDE = {
    "id", "upload_date", "risk_level",
    # 백엔드 자동 파생 — 원본값이 바뀌면 자동 재계산되므로 별도 기록하지 않음
    "egfr", "ldl_calc", "non_hdl", "homa_ir", "homa_beta",
    "tyg_index", "bmi_homa_ir", "pulse_pressure", "age",
    "dm_duration",
}


def _stringify(v) -> str | None:
    """감사 로그용 값 직렬화 — None 은 None 으로, 날짜는 ISO 문자열."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def _record_audit(db: Session, patient_id: int, field: str, old, new, actor: str = "system") -> None:
    """단일 필드 변경을 patient_audit 테이블에 기록.
    호출자가 이미 트랜잭션 내라고 가정 — commit 은 호출자가 처리."""
    db.add(PatientAudit(
        patient_id=patient_id,
        field_name=field,
        old_value=_stringify(old),
        new_value=_stringify(new),
        actor=actor,
    ))


def _current_age(p: Patient) -> int | None:
    """
    현재 만 나이 — dob 기반으로 매 조회마다 재계산.
    dob 가 없을 때만 stale 한 patient.age 컬럼으로 fallback.
    DB 의 patient.age 는 입력 시점의 값이라 해를 넘기면 어긋나므로 가능하면 항상 dob 에서 계산.
    """
    today = date.today()
    if p.dob is not None:
        a = today.year - p.dob.year - ((today.month, today.day) < (p.dob.month, p.dob.day))
        if 0 <= a <= 120:
            return a
    if p.age is not None:
        try:
            return int(p.age)
        except (TypeError, ValueError):
            return None
    return None


def _current_dm_duration(p: Patient) -> int | None:
    """
    현재 시점 당뇨 이환 기간 = 현재 만 나이 - 진단 시 나이.
    dob 가 있으면 시간이 흘러도 자동 갱신. patient.dm_duration 컬럼은 stale 가능하므로
    응답 시점에 재계산해서 덮어씀.
    """
    if p.dm_diagnosis_age is None:
        return None
    cur = _current_age(p)
    if cur is None:
        return None
    years = cur - int(p.dm_diagnosis_age)
    return years if 0 <= years <= 120 else None


def _apply_dynamic_age(data: dict, p: Patient) -> dict:
    """PatientResponse 직렬화 결과의 age / dm_duration 을 오늘 기준으로 갱신."""
    cur_age = _current_age(p)
    if cur_age is not None:
        data["age"] = cur_age
    cur_dur = _current_dm_duration(p)
    if cur_dur is not None:
        data["dm_duration"] = cur_dur
    return data


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aggregate_clinical_floor(patient: Patient) -> str | None:
    """
    환자 종합 risk_level 에만 적용되는 임상 안전망.
    개별 합병증 level 은 ML threshold 판단을 보존하고, 여기서는 환자 카드 등급만 보정한다.
    """
    hba1c = _safe_float(getattr(patient, "hba1c", None))
    cpep = _safe_float(getattr(patient, "c_peptide", None))

    if hba1c is not None and hba1c >= 11.0:
        return "중위험"
    if hba1c is not None and cpep is not None and hba1c >= 8.5 and cpep < 0.5:
        return "중위험"
    return None


def _compute_risk_level(patient: Patient) -> str | None:
    """
    환자 데이터로 최고 위험도 계산.
    POST / PATCH / CSV 업로드 시에만 호출되며, 결과는 Patient.risk_level 컬럼에 저장된다.
    목록 조회는 컬럼만 읽어 즉시 반환 (ML 재실행 X).

    v2.1.3 (Codex critical C1): 예측 예외/누락 시 "저위험" 으로 silent fallback 금지.
    예측 실패면 None 반환 → 컬럼에 NULL 저장 → UI 가 "분석실패" 로 명시 표시.
    환자 안전을 위해 모든 합병증 ML 점수가 없으면 그 환자의 위험도를 알 수 없는 것으로 처리.
    """
    try:
        pdict = {c.name: getattr(patient, c.name) for c in patient.__table__.columns}
        preds = predict_all(pdict)
        levels = [v["level"] for v in preds.values() if v.get("available") and v.get("level")]
        if not levels:
            # 모든 합병증 모델이 available=False → 명시적 None (분석실패)
            print(f"[WARN] _compute_risk_level: 환자 {getattr(patient, 'id', '?')} 모든 합병증 예측 실패 → NULL")
            return None
        # v2.1.4: predict_all 의 개별 합병증 level 최고값을 우선하고,
        # 강한 임상 신호는 환자 종합 risk_level 에만 최소 중위험으로 반영한다.
        # v2.1.3 (Codex C1): "분석실패" 도 levels 목록에 포함될 수 있음 → 정상 등급만 비교
        normalized = [lv for lv in levels if lv in ("고위험", "중위험", "저위험")]
        if not normalized:
            return None
        if "고위험" in normalized:
            return "고위험"
        if "중위험" in normalized:
            return "중위험"
        aggregate_floor = _aggregate_clinical_floor(patient)
        if aggregate_floor:
            return aggregate_floor
        return "저위험"
    except Exception as e:
        # 예측 예외 — 데이터 타입 / 모델 로드 실패 등. 환자 안전을 위해 silent 저위험 금지.
        print(f"[ERROR] _compute_risk_level 환자 {getattr(patient, 'id', '?')}: {type(e).__name__}: {e}")
        return None


def _ensure_risk_level(patient: Patient, db: Session) -> str | None:
    """risk_level 이 이미 있으면 그대로 반환, 없으면 계산 후 DB 에 저장.
    v2.1.3 (Codex C1): _compute_risk_level 이 None 반환하면 NULL 그대로 저장 (silent fallback 금지)."""
    if patient.risk_level:
        return patient.risk_level
    level = _compute_risk_level(patient)
    patient.risk_level = level  # None 이면 NULL 저장 → UI 가 "분석실패" 표시
    try:
        db.commit()
    except Exception:
        db.rollback()
    return level


def _backfill_risk_levels_bg(patient_ids: list[int]) -> None:
    """백그라운드로 NULL risk_level 을 채워넣는다. 첫 조회 후 다음 조회부터 빨라짐."""
    if not patient_ids:
        return
    db = SessionLocal()
    try:
        for pid in patient_ids:
            p = db.query(Patient).filter(Patient.id == pid).first()
            if p and not p.risk_level:
                p.risk_level = _compute_risk_level(p)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.get("/patients/count")
def count_patients(db: Session = Depends(get_db)):
    """환자 수 빠르게 조회 (empty-state 게이팅용)"""
    total = db.query(Patient).count()
    return {"data": {"count": total}, "success": True}


@router.get("/patients/backup")
def backup_patients(db: Session = Depends(get_db)):
    """
    전체 환자 데이터를 CSV 로 내보내기 (백업용).
    Settings 의 '환자 데이터 백업' 버튼에서 호출 — 삭제 전 안전장치.
    """
    patients = db.query(Patient).order_by(Patient.id).all()
    if not patients:
        raise HTTPException(status_code=404, detail="백업할 환자 데이터가 없습니다.")

    columns = [c.name for c in Patient.__table__.columns]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for p in patients:
        writer.writerow([getattr(p, c) for c in columns])

    payload = buf.getvalue().encode("utf-8-sig")  # BOM 추가 (엑셀 한글 호환)
    today = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"dbcare_patients_backup_{today}.csv"
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/patients")
def list_patients(
    background: BackgroundTasks,
    page: int = Query(1, ge=1),
    size: int = Query(8, ge=1, le=100),
    risk_level: str = Query(None),
    search: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    환자 목록 조회 — risk_level 은 사전 계산된 컬럼에서 바로 읽어 즉시 반환한다.
    risk_level 이 NULL 인 환자는 BackgroundTasks 로 비동기 보충 (이후 조회부터 즉시 반영).
    """
    query = db.query(Patient)

    # 검색: name, chart_no, phone OR 조건
    # phone 은 DB 에 "010-1111-2222" 로 저장되지만 검색어가 "01011112222"
    # 처럼 하이픈/공백 없이 들어와도 매칭되도록 양쪽에서 정규화 후 비교.
    if search:
        like = f"%{search}%"
        # 검색어에서 하이픈/공백 제거한 정규화 버전
        digits_only = "".join(ch for ch in search if ch.isdigit())
        phone_filters = [Patient.phone.ilike(like)]
        if digits_only:
            normalized_db_phone = func.replace(
                func.replace(func.replace(Patient.phone, "-", ""), " ", ""),
                ".",
                "",
            )
            phone_filters.append(normalized_db_phone.ilike(f"%{digits_only}%"))
        query = query.filter(
            or_(
                Patient.name.ilike(like),
                Patient.chart_no.ilike(like),
                *phone_filters,
            )
        )

    # risk_level 필터는 DB 레벨에서 처리 (사전 계산된 컬럼 사용)
    if risk_level:
        query = query.filter(Patient.risk_level == risk_level)

    total = query.count()
    patients = query.order_by(Patient.id).offset((page - 1) * size).limit(size).all()

    pending_ids: list[int] = []

    def _serialize(p: Patient):
        data = PatientResponse.model_validate(p).model_dump()
        data["id"] = p.id
        _apply_dynamic_age(data, p)  # age / dm_duration 을 오늘 기준으로 갱신
        # 컬럼에 값이 있으면 그대로, 없으면 일단 "저위험"으로 표시하고 백그라운드 채우기
        if p.risk_level:
            data["risk_level"] = p.risk_level
        else:
            data["risk_level"] = None  # 프론트에서 "분석중" 표시 가능
            pending_ids.append(p.id)
        return data

    results = [_serialize(p) for p in patients]

    # NULL 인 환자가 있으면 백그라운드로 채워넣기
    if pending_ids:
        background.add_task(_backfill_risk_levels_bg, pending_ids)

    return {
        "data": results,
        "total": total,
        "page": page,
        "size": size,
        "success": True,
    }


@router.get("/patients/{patient_id}")
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    measurements = (
        db.query(MeasurementHistory)
        .filter(MeasurementHistory.patient_id == patient_id)
        .order_by(MeasurementHistory.measured_at)
        .all()
    )

    pdata = PatientResponse.model_validate(patient).model_dump()
    pdata["id"] = patient.id
    _apply_dynamic_age(pdata, patient)  # age / dm_duration 을 오늘 기준으로 갱신
    # 상세 조회는 동기 계산 + 저장 (단일 환자라 부담 없음)
    pdata["risk_level"] = _ensure_risk_level(patient, db)

    return {
        "data": {
            "patient": pdata,
            "measurements": [MeasurementResponse.model_validate(m) for m in measurements],
        },
        "success": True,
    }


def _mirror_csv_bg(patient_id: int) -> None:
    """BackgroundTask 용 — 새 session 으로 export 한 뒤 닫는다."""
    db = SessionLocal()
    try:
        _export_patient_csv(db, patient_id)
    finally:
        db.close()


@router.post("/patients")
def create_patient(body: PatientCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    """
    수기 입력 / API 등록 (v2.1.2 — 동일 차트번호 + 다른 검사일 시 측정 추가 모드).

    동작 분기:
      1. 새 차트번호 → 환자 row 신규 생성 + 첫 측정 이력
      2. 기존 차트번호 + 같은 검사일(혹은 검사일 미입력) → 409 (중복)
      3. 기존 차트번호 + 다른 검사일 → 환자 row 의 lab 값 업데이트 + 측정 이력 추가

    CSV 미러는 BackgroundTask 로 비동기.
    """
    raw = body.model_dump()
    chart_no = (raw.get("chart_no") or "").strip()
    exam_date_str = raw.get("exam_date")  # ISO date string or None

    existing = None
    if chart_no:
        existing = db.query(Patient).filter(Patient.chart_no == chart_no).first()

    # ── 분기 2 — 동일 검사일 중복 ─────────────────────────────
    if existing and exam_date_str:
        # 기존 환자의 exam_date 또는 measurement_history 에 같은 날짜가 있으면 409
        from datetime import date as _date
        try:
            new_exam = _date.fromisoformat(str(exam_date_str)[:10])
        except (ValueError, TypeError):
            new_exam = None
        if new_exam is not None:
            same_date = db.query(MeasurementHistory).filter(
                MeasurementHistory.patient_id == existing.id,
                MeasurementHistory.measured_at == new_exam,
            ).first()
            if same_date or (existing.exam_date == new_exam):
                raise HTTPException(
                    status_code=409,
                    detail=f"동일 차트번호({chart_no}) + 동일 검사일({new_exam.isoformat()}) 기록이 이미 있습니다.",
                )
    elif existing and not exam_date_str:
        # 검사일 미입력 시 — 의도가 모호. 명시적 에러.
        raise HTTPException(
            status_code=409,
            detail=f"차트번호 {chart_no} 가 이미 등록되어 있습니다. 새 검사라면 '검사일'을 입력해주세요.",
        )

    # 파생 변수 자동 계산
    enriched = compute_derived(raw)
    patient_cols = {c.name for c in Patient.__table__.columns}
    payload = {k: v for k, v in enriched.items() if k in patient_cols}

    if existing:
        # ── 분기 3 — 기존 환자 lab 값 업데이트 (메타데이터는 보존) ──
        # 메타 (이름·생년월일·연락처·과거력) 는 사용자가 명시적으로 변경한 값만 덮어쓰지 않고,
        # 사실상 모두 update 한다 (불러오기 흐름에서 사용자가 동일 값 또는 수정값 보내므로).
        for k, v in payload.items():
            if k in ("id", "upload_date"):
                continue
            if v is not None:
                setattr(existing, k, v)
        existing.risk_level = _compute_risk_level(existing)
        db.commit()
        db.refresh(existing)
        patient = existing
        is_new = False
    else:
        # ── 분기 1 — 새 환자 row 생성 ─────────────────────────
        patient = Patient(**payload)
        if patient.upload_date is None:
            patient.upload_date = datetime.now()
        patient.risk_level = _compute_risk_level(patient)
        db.add(patient)
        db.commit()
        db.refresh(patient)
        is_new = True

    # ── 측정 이력 추가 (양쪽 분기 공통) ───────────────────────
    # v2.1.3 (Codex 리뷰): IntegrityError 명시 처리 — race condition 으로 unique constraint
    # 위반 시 조용히 삼키지 않고 의미 있는 동작 (이미 있으면 OK, 다른 에러는 raise).
    from sqlalchemy.exc import IntegrityError
    meas_date = patient.exam_date or (patient.upload_date.date() if patient.upload_date else date.today())
    if patient.hba1c is not None or patient.c_peptide is not None or patient.cr is not None:
        # 같은 날짜 중복 방지 (선체크 — 일반 케이스)
        dup = db.query(MeasurementHistory).filter(
            MeasurementHistory.patient_id == patient.id,
            MeasurementHistory.measured_at == meas_date,
        ).first()
        if not dup:
            mh = MeasurementHistory(
                patient_id=patient.id,
                measured_at=meas_date,
                hba1c=patient.hba1c,
                c_peptide=patient.c_peptide,
                cr=patient.cr,
            )
            db.add(mh)
            try:
                db.commit()
            except IntegrityError:
                # 동시 요청으로 race condition 발생 — 이미 같은 (patient_id, measured_at) row 있음.
                # 정상 중복으로 간주하고 응답은 성공으로 처리.
                db.rollback()
            except Exception as e:
                # 그 외 에러 — measurement 누락 응답하지 않도록 raise (환자 row 는 이미 commit 됨)
                db.rollback()
                print(f"[WARN] measurement insert 실패 (patient_id={patient.id}, date={meas_date}): {e}")

    background.add_task(_mirror_csv_bg, patient.id)

    return {
        "data": PatientResponse.model_validate(patient),
        "is_new": is_new,
        "success": True,
    }


@router.get("/patients/by-chart/{chart_no}")
def find_by_chart(chart_no: str, db: Session = Depends(get_db)):
    """
    수기 입력 폼의 "기존 환자 불러오기" 용 — 차트번호로 환자 찾아 메타데이터만 반환.
    환자 없으면 404, 있으면 PatientResponse 와 동일 형태.
    """
    p = db.query(Patient).filter(Patient.chart_no == chart_no.strip()).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"차트번호 {chart_no} 인 환자를 찾을 수 없습니다.")
    data = PatientResponse.model_validate(p).model_dump()
    data["id"] = p.id
    return {"data": data, "success": True}


# v2.2.2 (H2): PATCH 로 입력값 변경 시 재계산해야 하는 파생 컬럼.
#   PURE: 순수 계산값 — 항상 재계산, 계산 불가(None)면 stale 제거 위해 None 으로 clear.
#   SOFT: 계산값이지만 실측 제공 가능 — 계산되면 갱신, 불가하면 기존값 보존.
#   'ldl'(병원 실측치)은 어느 쪽도 아님 → 그대로 보존.
_PURE_DERIVED_FIELDS = (
    "ldl_calc", "non_hdl", "egfr",
    "homa_ir", "homa_beta", "tyg_index", "bmi_homa_ir", "pulse_pressure",
)
_SOFT_DERIVED_FIELDS = ("bmi", "he_insulin", "dm_duration")


def _recompute_derived(patient: Patient) -> None:
    """입력 필드 변경 후 파생 컬럼(eGFR/BMI/LDL_calc/HOMA/맥압 등)을 재계산해 stale 방지.
    예측은 patient_to_features 가 즉석 계산하지만, 화면/CSV/유사사례는 DB 컬럼을 직접 읽으므로
    여기서 컬럼까지 갱신해야 페이지 간 수치가 일치한다. (의료진 의아함 방지)

    v2.2.2 (codex 라운드2): 편집 모달이 파생필드(age/bmi/he_insulin 등)를 항상 전송하므로
    'changes 에 없을 때만' 재계산하면 영영 갱신 안 됨 → client 의 파생값은 무시하고 항상
    원본 입력값으로 재계산한다. 계산 불가 시 PURE 는 None clear(=stale 제거), SOFT 는 기존 보존."""
    raw = {c.name: getattr(patient, c.name) for c in patient.__table__.columns}
    old_soft = {f: raw.get(f) for f in _SOFT_DERIVED_FIELDS}
    for f in (*_PURE_DERIVED_FIELDS, *_SOFT_DERIVED_FIELDS):
        raw[f] = None  # 비워서 compute_derived 가 client 값 무시하고 새로 계산
    enriched = compute_derived(raw)
    for f in _PURE_DERIVED_FIELDS:
        setattr(patient, f, enriched.get(f))  # None 이면 clear → 잘못된 stale 값 제거
    for f in _SOFT_DERIVED_FIELDS:
        v = enriched.get(f)
        setattr(patient, f, v if v is not None else old_soft[f])  # 계산 가능시 갱신, 아니면 보존


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: int, body: PatientUpdate, background: BackgroundTasks, db: Session = Depends(get_db)):
    """환자 정보 부분 수정 — PatientDetail 페이지의 '데이터 수정' 모달에서 호출.
    변경된 필드는 patient_audit 테이블에 자동으로 기록된다 (N2).
    수정 후 CSV 미러도 비동기로 갱신."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    changes = body.model_dump(exclude_unset=True)

    # ── 1) 변경 전 값 스냅샷 (실제로 달라지는 것만 추려 audit 에 기록) ──
    diffs: list[tuple[str, object, object]] = []  # (field, old, new)
    for key, new_val in changes.items():
        if key in _AUDIT_EXCLUDE:
            continue
        if not hasattr(patient, key):
            continue
        old_val = getattr(patient, key)
        # 값이 동일하면 (None == None 포함) 기록 안 함
        if old_val == new_val:
            continue
        diffs.append((key, old_val, new_val))

    # ── 2) 실제 적용 ──
    _old_exam = patient.exam_date  # v2.2.7: 검사일 변경 시 기존 측정이력 행 이동에 사용
    for key, value in changes.items():
        if hasattr(patient, key):
            setattr(patient, key, value)

    # ── 2.5) v2.2.2 (H2): 파생값(eGFR/BMI/LDL_calc/HOMA/맥압/이환기간) 재계산 ──
    #   입력(cr·체중·지질·혈압 등) 변경이 화면 파생 수치에 반영되도록 DB 컬럼 갱신.
    _recompute_derived(patient)

    # ── 2.7) v2.2.7 (H6): 검사 수치(c_peptide/hba1c/cr)·검사일 변경 시 추이 차트 소스인
    #   measurement_history 의 '해당 검사일 방문' 행을 환자 현재값과 동기화한다.
    #   (이전엔 PATCH 가 Patient row 만 갱신 → 카드 최신값과 추이 차트 마지막 점이 영구 불일치)
    if {"c_peptide", "hba1c", "cr", "exam_date"} & set(changes.keys()):
        new_exam = patient.exam_date
        if new_exam is not None:   # 검사일이 비면 가짜 today 행을 만들지 않는다
            def _meas_at(d):
                return db.query(MeasurementHistory).filter(
                    MeasurementHistory.patient_id == patient.id,
                    MeasurementHistory.measured_at == d,
                ).first()
            target = _meas_at(new_exam)
            # 검사일 자체가 바뀐 경우: 새 날짜 행이 없고 기존(old) 방문 행이 있으면 그 행을 새 날짜로
            #   '이동'(중복 방문 생성 방지). 새 날짜에 이미 다른 방문이 있으면 그 행을 갱신한다.
            if target is None and "exam_date" in changes and _old_exam is not None and _old_exam != new_exam:
                moved = _meas_at(_old_exam)
                if moved is not None:
                    moved.measured_at = new_exam
                    target = moved
            if target is not None:
                target.c_peptide = patient.c_peptide
                target.hba1c = patient.hba1c
                target.cr = patient.cr
            elif any(v is not None for v in (patient.c_peptide, patient.hba1c, patient.cr)):
                db.add(MeasurementHistory(
                    patient_id=patient.id, measured_at=new_exam,
                    c_peptide=patient.c_peptide, hba1c=patient.hba1c, cr=patient.cr,
                ))

    # ── 3) 감사 로그 작성 (실제 변경된 필드만) ──
    for field, old, new in diffs:
        _record_audit(db, patient.id, field, old, new)

    # ── 4) risk_level 재계산 + 변경 시 별도 audit 기록 ──
    old_risk = patient.risk_level
    patient.risk_level = _compute_risk_level(patient)
    if old_risk != patient.risk_level:
        _record_audit(db, patient.id, "risk_level", old_risk, patient.risk_level, actor="system:ml")

    db.commit()
    db.refresh(patient)

    data = PatientResponse.model_validate(patient).model_dump()
    data["id"] = patient.id
    data["risk_level"] = patient.risk_level

    # CSV 미러 — 비동기
    background.add_task(_mirror_csv_bg, patient.id)

    return {"data": data, "success": True}


@router.get("/patients/{patient_id}/audit")
def get_patient_audit(
    patient_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """환자의 변경 이력 (최신순). PatientDetail '수정 이력' 카드용."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    rows = (
        db.query(PatientAudit)
        .filter(PatientAudit.patient_id == patient_id)
        .order_by(PatientAudit.changed_at.desc(), PatientAudit.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "data": [
            {
                "id": r.id,
                "patient_id": r.patient_id,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
                "field_name": r.field_name,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "actor": r.actor,
            }
            for r in rows
        ],
        "success": True,
    }


@router.delete("/patients/{patient_id}")
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # 방어적 명시 cascade — relationship cascade 만 믿으면 SQLite 의 FK 미설정 +
    # 일부 ORM 경로에서 고아 레코드가 남을 수 있음. 명시적으로 함께 삭제.
    db.query(MeasurementHistory).filter(MeasurementHistory.patient_id == patient_id).delete(
        synchronize_session=False
    )
    db.query(PatientAudit).filter(PatientAudit.patient_id == patient_id).delete(
        synchronize_session=False
    )
    db.delete(patient)
    db.commit()
    return {"data": {"deleted": patient_id}, "success": True}


@router.delete("/patients")
def clear_patients(db: Session = Depends(get_db)):
    """
    전체 환자 삭제 (Settings 의 DB 초기화 버튼용).

    BUGFIX v2.0.4 — 이전 구현은 `db.query(Patient).delete()` 만 호출했음.
    이는 SQL bulk delete 라서 ORM 의 `cascade='all, delete-orphan'` 이 작동하지 않고,
    measurement_history 와 patient_audit 행이 고아로 남았다.
    SQLite 가 환자 id 를 재사용하면 새 환자가 옛 환자의 측정 이력을 물려받아
    "1일치 데이터인데 6개월 추이가 그려지는" 버그가 발생.

    수정: 의존 테이블을 먼저 비우고 patients 를 비운다.
    """
    deleted_meas = db.query(MeasurementHistory).delete(synchronize_session=False)
    deleted_audit = db.query(PatientAudit).delete(synchronize_session=False)
    deleted = db.query(Patient).delete(synchronize_session=False)
    db.commit()
    return {
        "data": {
            "deleted_count": deleted,
            "deleted_measurements": deleted_meas,
            "deleted_audit_rows": deleted_audit,
        },
        "success": True,
    }
