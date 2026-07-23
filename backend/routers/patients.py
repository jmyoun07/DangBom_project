"""
환자 CRUD API
"""
import csv
import io
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError

from models.database import get_db, Patient, MeasurementHistory, PatientAudit, SessionLocal
from models.schemas import PatientCreate, PatientResponse, PatientListResponse, MeasurementResponse, PatientUpdate
from ml.predictor import predict_all
from services.derived import (
    CLINICAL_DATE_FIELDS,
    CLINICAL_RANGES,
    SNAPSHOT_FIELDS,
    compute_derived,
    sanitize_clinical_data,
    validate_clinical_date,
    validate_clinical_value,
    visit_snapshot,
)


def _patient_dict(patient) -> dict:
    """Patient ORM → 컬럼 dict (스냅샷/예측 입력용)."""
    return {c.name: getattr(patient, c.name) for c in patient.__table__.columns}

# v2.2.8 (병원 정책): 필수 검사 누락 환자의 risk_level 센티넬.
#   NULL(=분석중, 백그라운드 재계산 대상)과 구분 → 재계산 반복 방지 + UI 가 '데이터부족' 표시.
RISK_INSUFFICIENT = "데이터부족"
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


def _sanitize_api_input(raw: dict) -> tuple[dict, list[str], set[str]]:
    """POST/PATCH 입력에 공용 임상 가드를 적용한다.

    미래·비실재 날짜는 요청 전체를 거부한다. 이상 수치는 None으로 정제하되, PATCH가
    기존 정상값을 지우지 않도록 거부된 필드 집합도 함께 반환한다.
    """
    clean, warnings = sanitize_clinical_data(raw)
    invalid_dates = [
        field for field in CLINICAL_DATE_FIELDS
        if field in raw and raw.get(field) is not None and clean.get(field) is None
    ]
    if invalid_dates:
        raise HTTPException(
            status_code=422,
            # 기존 폼은 detail을 문자열로 표시하므로 객체를 보내 [object Object]가 되지 않게 한다.
            detail="; ".join(warnings) or f"유효하지 않은 날짜: {', '.join(sorted(invalid_dates))}",
        )
    rejected_fields = {
        field for field in CLINICAL_RANGES
        if field in raw and raw.get(field) is not None and clean.get(field) is None
    }
    if warnings:
        print(f"[WARN] 임상 입력값 제외: {'; '.join(warnings)}")
    return clean, warnings, rejected_fields


def _aggregate_clinical_floor(patient: Patient) -> str | None:
    """
    환자 종합 risk_level 에만 적용되는 임상 안전망.
    개별 합병증 level 은 ML threshold 판단을 보존하고, 여기서는 환자 카드 등급만 보정한다.
    """
    # (codex) apply_clinical_floor 의 실제 룰과 임계를 맞춘다. 이전에는 Rule 1(HbA1c≥11)을
    #   '중위험'으로만 보고, C-peptide 는 폐기된 0.5 기준을 써서 안전망 fallback 이 본 룰보다
    #   약했다(C-pep 0.5~1.0 을 저위험으로, HbA1c≥11 을 중위험으로 과소평가).
    from ml.predictor import CPEP_T1DM_SUSPECT
    hba1c = _safe_float(getattr(patient, "hba1c", None))
    cpep = _safe_float(getattr(patient, "c_peptide", None))

    if hba1c is not None and hba1c >= 11.0:      # Rule 1
        return "고위험"
    if hba1c is not None and hba1c >= 9.0:       # Rule 2
        return "중위험"
    if cpep is not None and cpep < CPEP_T1DM_SUSPECT:   # Rule 3 (참고범위 하한 미만)
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
        # v2.2.8: 필수 검사 누락(전부 insufficient_data) → '데이터부족' 센티넬 (추정 금지)
        if preds and all(v.get("risk_source") == "insufficient_data" for v in preds.values()):
            return RISK_INSUFFICIENT
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
    size: int = Query(8, ge=1, le=5000),  # v2.2.8: 프론트가 전량 조회 후 클라이언트 페이징 → 상한 상향
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

    # v2.2.9: 한 행의 직렬화 실패가 목록 전체를 500 시키지 않도록 행별 방어.
    #   (스키마 제약은 위에서 해제했지만, 예기치 못한 값에도 최소 식별정보로 표시)
    results = []
    for p in patients:
        try:
            results.append(_serialize(p))
        except Exception as e:
            print(f"[WARN] _serialize 실패 id={getattr(p,'id','?')}: {type(e).__name__}: {e}")
            results.append({
                "id": p.id, "name": getattr(p, "name", None), "chart_no": getattr(p, "chart_no", None),
                "risk_level": getattr(p, "risk_level", None), "_serialize_error": True,
            })

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
    # v2.2.9 (#6): exclude_unset — 보내지 않은 플래그(hypertension/dm_medication/smoking 등)가
    #   기본값 0 으로 채워져 기존 1 을 덮어쓰던 문제 차단. (PATCH 는 이미 exclude_unset=True)
    raw, validation_warnings, _ = _sanitize_api_input(body.model_dump(exclude_unset=True))
    chart_no = (raw.get("chart_no") or "").strip()
    visit_date = raw.get("exam_date")

    existing = None
    if chart_no:
        existing = db.query(Patient).filter(Patient.chart_no == chart_no).first()

    # ── 분기 2 — 동일 검사일 중복 ─────────────────────────────
    if existing and visit_date:
        # 방문 이력이 권위 소스다. stale한 Patient.exam_date만 같은 경우에는 복구 가능한 입력을 막지 않는다.
        same_date = db.query(MeasurementHistory).filter(
            MeasurementHistory.patient_id == existing.id,
            MeasurementHistory.measured_at == visit_date,
        ).first()
        if same_date:
            raise HTTPException(
                status_code=409,
                detail=f"동일 차트번호({chart_no}) + 동일 검사일({visit_date.isoformat()}) 기록이 이미 있습니다.",
            )
    elif existing and not visit_date:
        # 검사일 미입력 시 — 의도가 모호. 명시적 에러.
        raise HTTPException(
            status_code=409,
            detail=f"차트번호 {chart_no} 가 이미 등록되어 있습니다. 새 검사라면 '검사일'을 입력해주세요.",
        )

    # 원본 검증 뒤 파생값 계산, 계산된 BMI/LDL도 같은 화이트리스트로 2차 검증한다.
    enriched = compute_derived(raw)
    enriched, derived_warnings = sanitize_clinical_data(enriched)
    validation_warnings.extend(derived_warnings)
    patient_cols = {c.name for c in Patient.__table__.columns}
    payload = {k: v for k, v in enriched.items() if k in patient_cols}

    # 환자와 방문을 한 트랜잭션에서 저장해 어느 한쪽만 남는 상태를 차단한다.
    meas_date = visit_date or date.today()  # IntegrityError가 조기 발생해도 오류 응답에 쓸 안전한 기본값
    try:
        if existing:
            patient = existing
            is_new = False
            latest_before = db.query(func.max(MeasurementHistory.measured_at)).filter(
                MeasurementHistory.patient_id == existing.id,
                MeasurementHistory.measured_at <= date.today(),
            ).scalar()
            is_latest = latest_before is None or visit_date >= latest_before
            if is_latest:
                # 핵심 4값/exam_date는 아래 sync만 변경한다. 그 외 이번 방문의 유효 입력만 반영.
                for k, v in payload.items():
                    if k in {"id", "upload_date", "risk_level", "exam_date", *_LATEST_VISIT_MASTER_FIELDS}:
                        continue
                    if v is not None:
                        setattr(existing, k, v)
                existing.risk_level = None
        else:
            patient = Patient(**payload)
            if patient.upload_date is None:
                patient.upload_date = datetime.now()
            db.add(patient)
            is_new = True

        db.flush()  # 신규 patient.id 확보
        meas_date = visit_date or patient.exam_date or (
            patient.upload_date.date() if patient.upload_date else date.today()
        )
        core = {field: payload.get(field) for field in _LATEST_VISIT_MASTER_FIELDS}
        if any(value is not None for value in core.values()):
            db.add(MeasurementHistory(
                patient_id=patient.id,
                measured_at=meas_date,
                snapshot=visit_snapshot(payload),  # 그 방문 입력만 저장(마스터의 미측정값 혼입 금지)
                **core,
            ))
            db.flush()
            sync_patient_from_latest_visit(db, patient)
        else:
            _recompute_derived(patient)
            patient.risk_level = _compute_risk_level(patient)

        db.commit()
        db.refresh(patient)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"동일 차트번호({chart_no}) 또는 동일 검사일({meas_date}) 기록이 이미 있습니다.",
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    background.add_task(_mirror_csv_bg, patient.id)

    return {
        "data": PatientResponse.model_validate(patient),
        "is_new": is_new,
        "warnings": validation_warnings,
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


def _recompute_derived(patient: Patient, *, preserve_bmi: bool = False) -> None:
    """입력 필드 변경 후 파생 컬럼(eGFR/BMI/LDL_calc/HOMA/맥압 등)을 재계산해 stale 방지.
    예측은 patient_to_features 가 즉석 계산하지만, 화면/CSV/유사사례는 DB 컬럼을 직접 읽으므로
    여기서 컬럼까지 갱신해야 페이지 간 수치가 일치한다. (의료진 의아함 방지)

    v2.2.2 (codex 라운드2): 편집 모달이 파생필드(age/bmi/he_insulin 등)를 항상 전송하므로
    'changes 에 없을 때만' 재계산하면 영영 갱신 안 됨 → client 의 파생값은 무시하고 항상
    원본 입력값으로 재계산한다. 계산 불가 시 PURE 는 None clear(=stale 제거), SOFT 는 기존 보존."""
    raw = {c.name: getattr(patient, c.name) for c in patient.__table__.columns}
    old_soft = {f: raw.get(f) for f in _SOFT_DERIVED_FIELDS}
    if raw.get("dob") is not None:
        # exam_date가 최신 방문으로 바뀌면 저장 age/eGFR도 그 방문 시점 나이로 다시 계산한다.
        raw["age"] = None
    for f in (*_PURE_DERIVED_FIELDS, *_SOFT_DERIVED_FIELDS):
        if preserve_bmi and f == "bmi":
            continue  # 최신 방문의 BMI는 키·몸무게 재계산값보다 권위 있는 실측값이다.
        raw[f] = None  # 비워서 compute_derived 가 client 값 무시하고 새로 계산
    enriched = compute_derived(raw)
    enriched, _ = sanitize_clinical_data(enriched)
    if raw.get("dob") is not None and enriched.get("age") is not None:
        patient.age = int(enriched["age"])
    for f in _PURE_DERIVED_FIELDS:
        setattr(patient, f, enriched.get(f))  # None 이면 clear → 잘못된 stale 값 제거
    for f in _SOFT_DERIVED_FIELDS:
        if preserve_bmi and f == "bmi":
            continue
        v = enriched.get(f)
        setattr(patient, f, v if v is not None else old_soft[f])  # 계산 가능시 갱신, 아니면 보존


_LATEST_VISIT_MASTER_FIELDS = ("hba1c", "c_peptide", "cr", "bmi", "dm_med_count")


def sync_patient_from_latest_visit(
    db: Session,
    patient: Patient,
    *,
    recompute_risk: bool = True,
) -> bool:
    """가장 최근의 유효 방문을 Patient 핵심 현재값과 동기화한다.

    전용 컬럼 또는 snapshot에서 실제 측정되고 임상 범위를 통과한 4개 핵심값만 반영한다.
    최신 방문에서 빠진 값은 기존 마스터값을 보존하며, 혈압·키·몸무게·생년월일 같은
    마스터 전용 값은 건드리지 않는다. commit은 호출자가 담당한다.
    """
    # SessionLocal(autoflush=False)에서도 직전에 추가/수정한 방문이 조회되도록 보장.
    db.flush()
    latest = (
        db.query(MeasurementHistory)
        .filter(
            MeasurementHistory.patient_id == patient.id,
            MeasurementHistory.measured_at <= date.today(),
        )
        .order_by(MeasurementHistory.measured_at.desc(), MeasurementHistory.id.desc())
        .first()
    )
    if latest is None:
        return False

    measured = _visit_measured(latest)
    changed = False
    for field in _LATEST_VISIT_MASTER_FIELDS:
        value = measured.get(field)
        if value is None:  # 그 방문에서 안 쟀거나 검증 실패한 항목은 기존값 보존
            continue
        if getattr(patient, field) != value:
            setattr(patient, field, value)
            changed = True

    if patient.exam_date != latest.measured_at:
        patient.exam_date = latest.measured_at
        changed = True

    if changed:
        # Cr/C-peptide/BMI/검사일 변화에 종속된 eGFR/HOMA/나이계열 값을 먼저 맞춘다.
        _recompute_derived(patient, preserve_bmi=True)
    if not recompute_risk and (changed or patient.risk_level is None):
        # 대량 업로드는 commit 후 기존 BackgroundTask가 계산하도록 명시적으로 무효화한다.
        patient.risk_level = None
    elif changed or patient.risk_level is None:
        patient.risk_level = _compute_risk_level(patient)
    return changed


def _patch_visit_snapshot(visit: MeasurementHistory, changes: dict) -> None:
    """기존 snapshot에서 PATCH된 방문 필드만 교체/삭제하고 행 날짜와 일치시킨다."""
    try:
        snapshot = json.loads(visit.snapshot) if visit.snapshot else {}
        if not isinstance(snapshot, dict):
            snapshot = {}
    except Exception:
        snapshot = {}
    for field in SNAPSHOT_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if value is None:
            snapshot.pop(field, None)  # NULL 컬럼 뒤에서 예전 snapshot 값이 부활하지 않게 제거
        else:
            snapshot[field] = value
    snapshot["exam_date"] = visit.measured_at
    visit.snapshot = visit_snapshot(snapshot)


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: int, body: PatientUpdate, background: BackgroundTasks, db: Session = Depends(get_db)):
    """환자 정보 부분 수정 — PatientDetail 페이지의 '데이터 수정' 모달에서 호출.
    변경된 필드는 patient_audit 테이블에 자동으로 기록된다 (N2).
    수정 후 CSV 미러도 비동기로 갱신."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    changes, validation_warnings, rejected_fields = _sanitize_api_input(
        body.model_dump(exclude_unset=True)
    )
    # 이상값은 경고만 남기고 PATCH 대상에서 제외해 기존 정상값/방문을 지우지 않는다.
    for field in rejected_fields:
        changes.pop(field, None)

    old_risk = patient.risk_level
    source_visit = (
        db.query(MeasurementHistory)
        .filter(
            MeasurementHistory.patient_id == patient.id,
            MeasurementHistory.measured_at <= date.today(),
        )
        .order_by(MeasurementHistory.measured_at.desc(), MeasurementHistory.id.desc())
        .first()
    )
    visit_keys = {*_LATEST_VISIT_MASTER_FIELDS, "exam_date"}
    new_visit_exam = changes.get("exam_date")
    if source_visit is None and new_visit_exam is None:
        # stale/future master exam_date를 새 방문일로 재사용하지 않는다.
        new_visit_exam, _ = validate_clinical_date(patient.exam_date, field="exam_date")

    if source_visit is None and visit_keys & set(changes):
        has_measured_core = any(
            field in changes and changes.get(field) is not None
            for field in _LATEST_VISIT_MASTER_FIELDS
        )
        if new_visit_exam is None or not has_measured_core:
            raise HTTPException(
                status_code=422,
                detail="방문 이력이 없는 환자의 검사값 수정에는 검사일과 최소 1개 실측값이 필요합니다.",
            )

    # 최신 방문 날짜를 이미 존재하는 다른 방문일로 옮기면 두 방문이 합쳐지므로 명시적으로 거부.
    if "exam_date" in changes and changes.get("exam_date") is not None and source_visit is not None:
        new_exam = changes["exam_date"]
        if new_exam != source_visit.measured_at:
            collision = db.query(MeasurementHistory).filter(
                MeasurementHistory.patient_id == patient.id,
                MeasurementHistory.measured_at == new_exam,
                MeasurementHistory.id != source_visit.id,
            ).first()
            if collision is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"검사일 {new_exam.isoformat()} 방문이 이미 존재합니다.",
                )

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
    for key, value in changes.items():
        if key in visit_keys:
            continue  # 핵심 4값/exam_date는 아래 방문 수정 후 sync만 Patient에 반영한다.
        if hasattr(patient, key):
            setattr(patient, key, value)

    # ── 2.5) v2.2.2 (H2): 파생값(eGFR/BMI/LDL_calc/HOMA/맥압/이환기간) 재계산 ──
    #   입력(cr·체중·지질·혈압 등) 변경이 화면 파생 수치에 반영되도록 DB 컬럼 갱신.
    _recompute_derived(patient)

    # ── 2.7) v2.2.7 (H6): 검사 수치(c_peptide/hba1c/cr)·검사일 변경 시 추이 차트 소스인
    #   measurement_history 의 '해당 검사일 방문' 행을 환자 현재값과 동기화한다.
    #   (이전엔 PATCH 가 Patient row 만 갱신 → 카드 최신값과 추이 차트 마지막 점이 영구 불일치)
    snapshot_changes = set(SNAPSHOT_FIELDS) & set(changes)
    if visit_keys & set(changes) or (source_visit is not None and snapshot_changes):
        target = source_visit
        if "exam_date" in changes and changes.get("exam_date") is not None and target is not None:
            target.measured_at = changes["exam_date"]

        if target is None:
            core_changes = {
                field: changes.get(field)
                for field in _LATEST_VISIT_MASTER_FIELDS
                if field in changes
            }
            if new_visit_exam is not None and any(value is not None for value in core_changes.values()):
                target = MeasurementHistory(
                    patient_id=patient.id,
                    measured_at=new_visit_exam,
                    **core_changes,
                )
                db.add(target)

        if target is not None:
            for field in _LATEST_VISIT_MASTER_FIELDS:
                if field in changes:
                    setattr(target, field, changes[field])
            _patch_visit_snapshot(target, changes)

    # ── 3) 방문 변경을 flush한 뒤 실제 최신 방문으로 마스터/risk_level 단일 동기화 ──
    patient.risk_level = None
    try:
        db.flush()
        sync_patient_from_latest_visit(db, patient)
        if patient.risk_level is None:  # 방문 이력이 전혀 없는 환자
            patient.risk_level = _compute_risk_level(patient)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="동일 검사일 방문이 이미 존재합니다.")
    except Exception:
        db.rollback()
        raise

    # 요청값이 아니라 최신 방문 동기화까지 끝난 실제 최종값을 감사 로그에 남긴다.
    for field, old, _requested in diffs:
        final = getattr(patient, field)
        if old != final:
            _record_audit(db, patient.id, field, old, final)
    if old_risk != patient.risk_level:
        _record_audit(db, patient.id, "risk_level", old_risk, patient.risk_level, actor="system:ml")

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="동일 검사일 방문이 이미 존재합니다.")
    except Exception:
        db.rollback()
        raise
    db.refresh(patient)

    data = PatientResponse.model_validate(patient).model_dump()
    data["id"] = patient.id
    data["risk_level"] = patient.risk_level

    # CSV 미러 — 비동기
    background.add_task(_mirror_csv_bg, patient.id)

    return {"data": data, "warnings": validation_warnings, "success": True}


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


# 검사이력 페이지 — 질환 모델명 → UI 짧은 키
_VISIT_DISEASE_KEYS = {
    "kidney_disease": "kidney", "retinopathy": "retina", "cardiovascular": "cardio",
    "neuropathy": "neuro", "cerebrovascular": "cerebro", "dementia": "dementia",
}


# 방문 시점 기준으로 반드시 재계산해야 하는 값 — 환자 프로필의 '현재' 파생값을 그대로 쓰면
#   과거 방문을 최신 eGFR/HOMA/나이로 예측하는 시점 오염이 생긴다.
_RECOMPUTE_KEYS = frozenset({
    "egfr", "ldl_calc", "non_hdl", "homa_ir", "homa_beta", "tyg_index",
    "bmi_homa_ir", "pulse_pressure", "he_insulin", "age", "dm_duration",
})

# (codex) 시점 오염 차단 대상 — 방문마다 실제로 측정되는 검사값.
#   이것들이 환자 '현재값'으로 base 에 남으면 2021년 방문을 2026년 지질로 예측하는 미래 참조가 된다.
#   단, 아예 결측으로 두면 필수검사 게이트(REQUIRED_CLINICAL_FIELDS)에 걸려 예측 자체가 불가하므로
#   '그 환자가 언젠가 실측한 값'이 있으면 시간적으로 가장 가까운 관측치로 채운다(LOCF + 최초관측 역보간).
#   혈압·키·몸무게는 OCR 방문 데이터에 없어(마스터행에만 존재) 여기서 제외 — 마스터값 사용이 불가피.
_TIME_VARYING_LABS = frozenset({
    "fbg", "ldl", "total_cholesterol", "triglycerides", "hdl",
    "alt", "ast", "ggt",
    "he_upro", "he_uglu", "he_ubld", "urine_bil", "urine_uro",
    "urine_ket", "urine_nit", "urine_ph", "urine_sg",
})


def _visit_measured(v) -> dict:
    """그 방문의 검증된 실측값만 반환한다.

    snapshot을 먼저 읽되 4개 전용 컬럼이 non-NULL이면 그 값의 유효성 여부와 무관하게
    snapshot 값을 제거한 뒤 컬럼만 검증한다. 즉 컬럼과 snapshot이 모두 있으면 컬럼이
    명시적으로 우선하며, invalid 컬럼을 valid snapshot으로 몰래 대체하지 않는다.
    """
    measured = {}
    if v.snapshot:
        try:
            raw_snapshot = json.loads(v.snapshot)
            if not isinstance(raw_snapshot, dict):
                raw_snapshot = {}
            clean_snapshot, _ = sanitize_clinical_data(raw_snapshot)
            for k, val in clean_snapshot.items():
                if val is not None:
                    measured[k] = val
        except Exception:
            pass
    for k, col in (("hba1c", v.hba1c), ("c_peptide", v.c_peptide), ("cr", v.cr), ("bmi", v.bmi)):
        if col is not None:
            measured.pop(k, None)  # non-NULL 컬럼은 snapshot fallback을 차단한다.
            value, _ = validate_clinical_value(k, col)
            if value is not None:
                measured[k] = value
    return measured


def _visit_data_series(visits, pdict) -> list:
    """방문별 '그 시점 전체 데이터' dict 목록 — LOCF(직전 측정값 이월).

    병원은 HbA1c 는 매 방문, C-peptide·생화학은 3~6개월 주기로 측정한다. 따라서 안 잰 항목은
    '직전에 측정한 값이 유지된다'고 보는 게 임상적으로 맞다(Last Observation Carried Forward).
    (이전 구현은 결측을 '현재(최신)값'으로 채워 2021년 방문을 2025년 C-peptide 로 예측하는
     미래 참조 오류가 있었다.)

    - 아직 한 번도 측정된 적 없는 시계열 검사값은 결측으로 둔다(최신값을 끌어오지 않음).
    - eGFR/HOMA/TyG/나이 등 파생값은 그 방문의 실측 기준으로 재계산.
    """
    base = {
        k: val for k, val in pdict.items()
        if k not in _RECOMPUTE_KEYS
        and k not in _TIME_VARYING_LABS
        and k not in _LATEST_VISIT_MASTER_FIELDS
    }
    measured_per_visit = [_visit_measured(v) for v in visits]

    # 최초 관측 역보간(NOCB) — 첫 실측 이전 방문은 '그 환자의 가장 이른 실측치'로 채운다.
    #   최신값(수년 뒤)을 끌어오는 것보다 시간적으로 훨씬 가까워 오염이 작고,
    #   필수검사 게이트를 통과해 예측이 가능해진다. 실측이 아예 없는 항목만 마스터값 사용.
    #   대상은 '방문마다 측정되는 모든 항목' — 병원이 생화학(Cr)·C-peptide 를 3~6개월 주기로 재서
    #   초진에 없는 경우가 많다(Cr 46명·C-pep 32명). 이때 가장 이른 실측치를 baseline 으로 쓰는 것이
    #   임상적으로 타당하고, 새 방문이 쌓여도 값이 바뀌지 않아 '초진 기준 고정' 요건도 만족한다.
    _nocb_fields = set(_TIME_VARYING_LABS)
    for m in measured_per_visit:
        _nocb_fields.update(k for k in m if k not in _RECOMPUTE_KEYS)
    seed = {}
    for k in _nocb_fields:
        for m in measured_per_visit:
            if m.get(k) is not None:
                seed[k] = m[k]
                break
        else:
            if pdict.get(k) is not None:
                seed[k] = pdict[k]

    carry = dict(seed)   # LOCF 누적 — 지금까지 측정된 최신 검사값
    series = []
    for v, _m in zip(visits, measured_per_visit):
        carry.update(_visit_measured(v))
        # carry 에 실린 나이/파생값은 그 방문 시점 기준으로 다시 뽑아야 하므로 제거 후 재계산.
        carried = {k: val for k, val in carry.items() if k not in _RECOMPUTE_KEYS}
        data = compute_derived({**base, **carried, "exam_date": v.measured_at})
        # dob 가 없어 방문 시점 나이를 못 구하면 저장 프로필 값으로 fallback.
        if data.get("age") is None:
            data["age"] = pdict.get("age")
        if data.get("dm_duration") is None:
            data["dm_duration"] = pdict.get("dm_duration")
        # (codex) predict_all 의 _normalize_age_duration 이 dob 로 '오늘 나이'를 다시 계산해
        #   방문 시점 나이를 덮어쓴다(과거 방문 264/571 건이 최대 14년 미래 나이로 예측됨).
        #   dob 를 빼서 위에서 구한 방문 시점 age/dm_duration 이 그대로 쓰이게 고정한다.
        data.pop("dob", None)
        series.append(data)
    return series


def _visit_full_values(v, pdict) -> dict:
    """방문 1건의 전체 검사값 dict (단건 조회용 — 초진 시나리오 기준값 등)."""
    return _visit_data_series([v], pdict)[0]


def _build_visit_series(visits, pdict) -> list:
    """방문 리스트 → 방문별 {measured_at, visit_type, has_snapshot, measured, values, metrics, risk} 배열.

    - values   : LOCF 로 채운 '그 시점 전체 데이터' (예측 입력)
    - measured : 그날 실제 측정된 값만 (검사수치 표는 이걸 써야 이월값을 실측처럼 보여주지 않음)
    risk 는 방문 데이터로 predict_all 실행한 6합병증 {level, available, score}. (/visits·통합리포트 공유)
    """
    datas = _visit_data_series(visits, pdict)
    out = []
    for i, (v, vdata) in enumerate(zip(visits, datas)):
        measured = _visit_measured(v)
        try:
            preds = predict_all(dict(vdata))
        except Exception:
            preds = {}
        risk = {}
        for mname, short in _VISIT_DISEASE_KEYS.items():
            p = preds.get(mname) or {}
            risk[short] = {
                "level": p.get("level"),
                "available": bool(p.get("available")),
                "score": p.get("display_score") if p.get("display_score") is not None else p.get("score"),
                "raw_score": p.get("raw_score") if p.get("raw_score") is not None else p.get("score"),
            }
        out.append({
            "measured_at": v.measured_at.isoformat() if v.measured_at else None,
            "visit_type": "초진" if i == 0 else "재진",  # 최신도 재진(졸업 개념 제거 — 병원 피드백)
            "has_snapshot": bool(v.snapshot),
            "measured": measured,
            "values": vdata,
            "metrics": {k: measured.get(k) for k in _LATEST_VISIT_MASTER_FIELDS},
            "risk": risk,
        })
    return out


@router.get("/patients/{patient_id}/visits")
def patient_visits(patient_id: int, db: Session = Depends(get_db)):
    """검사이력 페이지용 — 방문별 전체 검사값 + 방문별 합병증 위험도.

    snapshot(방문 전체값)이 있으면 그대로 사용, 없으면(과거행) 현재 환자값에 방문의
    4핵심지표(HbA1c/C-peptide/Cr/BMI)를 덮어써 근사한다. 위험도는 방문 데이터로 predict_all 실행.
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    visits = (
        db.query(MeasurementHistory)
        .filter(MeasurementHistory.patient_id == patient_id)
        .order_by(MeasurementHistory.measured_at)
        .all()
    )
    pdict = _patient_dict(patient)
    _apply_dynamic_age(pdict, patient)  # age 오늘 기준 최신화

    out = _build_visit_series(visits, pdict)

    return {"data": {
        "patient": {
            "id": patient.id, "name": patient.name, "chart_no": patient.chart_no,
            "sex": pdict.get("sex"), "age": pdict.get("age"),
        },
        "current": pdict,
        "visits": out,
    }, "success": True}


@router.get("/patients/{patient_id}/integrated-report")
def integrated_report(patient_id: int, db: Session = Depends(get_db)):
    """통합 리포트 페이지용 — 환자 식별(+첫/최근 검사일) + 방문 시계열(6합병증 score·검사값)
    + 초진(첫 검사) 스냅샷 기준 시나리오 3종(현재유지/집중관리/졸업).

    시나리오는 반드시 '초진 데이터 기준'이라 최신 검사가 추가돼도 불변이어야 한다(스펙 공통주의 #1).
    → 첫 검사 스냅샷을 baseline=sim 으로 build_scenario_payload 에 넘겨 slider drift=0 로 고정.
    """
    # 지연 import — routers.scenario 와의 순환 방지(모듈 로드 순서 무관).
    from routers.scenario import build_scenario_payload
    from services.derived import current_age as _derived_age

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    visits = (
        db.query(MeasurementHistory)
        .filter(MeasurementHistory.patient_id == patient_id)
        .order_by(MeasurementHistory.measured_at)
        .all()
    )
    pdict = _patient_dict(patient)
    _apply_dynamic_age(pdict, patient)  # 표시 age/dm_duration 오늘 기준

    series = _build_visit_series(visits, pdict)

    first_dt = visits[0].measured_at if visits else None
    last_dt = visits[-1].measured_at if visits else None

    # ── 초진 스냅샷 기준 시나리오 3종 ──
    # (codex) '스냅샷 문자열 존재' 만으로 정확도를 판정하면 안 된다 — 현재 90명 전원이
    #   부분 스냅샷(일부 항목만 실측)인데 전부 '정확'으로 보고됐다. 시나리오에 실제로 쓰이는
    #   핵심 항목이 초진에 실측됐는지로 판정한다.
    _SCENARIO_KEY_FIELDS = ("hba1c", "c_peptide", "cr", "bmi", "sbp", "dbp")
    scenarios = None
    first_measured = _visit_measured(visits[0]) if visits else {}
    first_has_snapshot = bool(visits) and all(
        first_measured.get(k) is not None for k in _SCENARIO_KEY_FIELDS
    )
    if visits:
        # 초진 전체값 — 이미 계산된 방문 시계열의 첫 항목을 쓴다.
        #   (단건으로 _visit_full_values 를 부르면 NOCB seed 가 다른 방문을 못 봐서, 초진에
        #    Cr·C-peptide 를 안 잰 환자 46명이 통째로 insufficient 가 된다.)
        snap0 = series[0]["values"]
        # (codex) 0.0 을 결측으로 오인하지 않게 명시적 None 체크. c_peptide=0.0(극저)도 보존.
        fh = _safe_float(snap0.get("hba1c"))
        if fh is None:
            fh = _safe_float(patient.hba1c)
        if fh is None:
            fh = 7.5
        fc = _safe_float(snap0.get("c_peptide"))
        if fc is None:
            fc = _safe_float(patient.c_peptide)
        if fc is None:
            fc = 2.0
        # 초진 나이: 스냅샷 age(첫 검사 시점) 우선 → dob 로 첫검사일 만나이 → 저장 age → 60.
        # (codex) measured_at 는 Date 컬럼이라 .date() 없음 → datetime 일 때만 .date() 호출.
        age0 = snap0.get("age")
        if not age0 and first_dt is not None:
            _on = first_dt.date() if isinstance(first_dt, datetime) else first_dt
            age0 = _derived_age({"dob": patient.dob}, on=_on)
        age0 = age0 or patient.age or 60
        # (codex) '초진 고정' — predict_all(_normalize_age_duration)이 dob 로 '오늘 나이'를
        #   다시 계산해 초진 시나리오가 조회일 기준으로 드리프트하는 것을 막는다. dob 를 제거하고
        #   age 를 age0 으로 못박아 ML score·floor·dm_duration 모두 첫 검사 시점으로 동결.
        snap_frozen = {**snap0, "age": age0}
        snap_frozen.pop("dob", None)
        scenarios = build_scenario_payload(
            patient, snap_frozen, age0,
            sim_hba1c=fh, sim_cpep=fc, base_hba1c=fh, base_cpep=fc,
        )

    patient_card = {
        "id": patient.id, "name": patient.name, "chart_no": patient.chart_no,
        "sex": pdict.get("sex"), "age": pdict.get("age"),
        "dob": patient.dob.isoformat() if getattr(patient, "dob", None) else None,
        "phone": getattr(patient, "phone", None),
        "dm_duration": pdict.get("dm_duration"),
        "first_exam_date": first_dt.isoformat() if first_dt else None,
        "last_exam_date": last_dt.isoformat() if last_dt else None,
        "risk_level": patient.risk_level,
    }

    return {"data": {
        "patient": patient_card,
        "current": pdict,
        "visits": series,
        "scenarios": scenarios,  # {radar, neglect, intensive, graduation, risk_thresholds, ...} | None
        # (codex) 첫 방문에 스냅샷이 없으면 초진 시나리오는 현재값+초진 4지표로 근사한 것이라
        #   완전한 '초진 고정'이 아님을 프론트가 표시할 수 있게 플래그로 알림.
        "scenarios_approximate": bool(scenarios) and not first_has_snapshot,
    }, "success": True}


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
