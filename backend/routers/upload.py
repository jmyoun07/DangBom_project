"""
CSV 업로드 API — 3000명 규모 일괄 업로드 지원.

업로드 의미론 (v2.3 — 같은 chart_no = 동일 환자의 반복 방문):
  - 한 행 = 한 번의 검사 방문 (exam_date 기준)
  - 신규 chart_no    → Patient 생성 + MeasurementHistory 첫 기록
  - 기존 chart_no    → 같은 exam_date 가 이미 있으면 skip,
                        아니면 MeasurementHistory 에 새 방문 추가
                        + 이 방문이 현재 최신이면 Patient row 도 최신값으로 갱신
                        (과거 데이터 소급 입력이면 Patient 는 건드리지 않음)
  - skip: 같은 (chart_no, exam_date) 가 이미 존재하는 경우만

리다이렉트 판단:
  - 영향받은 고유 환자 수 == 1  → 해당 환자 대시보드
  - 영향받은 고유 환자 수 >  1  → 환자 목록

성능:
  - existing chart_no 한 번에 조회 (IN 쿼리)
  - 단일 commit — 3000행도 수 초 내
  - ML risk_level 은 BackgroundTasks 로 비동기 처리
"""
import io
from datetime import datetime, date
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.orm import Session
import pandas as pd

from models.database import get_db, Patient, MeasurementHistory
from routers.patients import _backfill_risk_levels_bg
from services.derived import compute_derived, normalize_sex


def _append_measurement(db: Session, patient_id: int, pdata: dict) -> None:
    """
    기존 환자에 시계열 측정값을 누적 저장.
    C-peptide / HbA1c / Cr 3가지 핵심 추적 지표만 기록 (대시보드 차트와 일치).
    """
    measured_at = pdata.get("exam_date") or date.today()
    cp = pdata.get("c_peptide")
    a1c = pdata.get("hba1c")
    cr = pdata.get("cr")
    # 3개 지표가 모두 없으면 측정 기록을 만들지 않음
    if cp is None and a1c is None and cr is None:
        return
    db.add(MeasurementHistory(
        patient_id=patient_id,
        measured_at=measured_at,
        c_peptide=cp,
        hba1c=a1c,
        cr=cr,
    ))

router = APIRouter(prefix="/api/v1", tags=["upload"])

# 메타데이터 컬럼 (프로그램 운영용) — ML 알고리즘에는 사용 X
META_FIELDS = {"name", "chart_no", "phone", "exam_date", "dob"}

# CSV 컬럼 -> DB 필드 매핑
# ML 독립변수 + 운영 메타데이터 모두 포함
CSV_COLUMN_MAP = {
    # ── 메타데이터 (프로그램 운영용) ──
    "name": "name",
    "이름": "name",
    "chart_no": "chart_no",
    "차트번호": "chart_no",
    "phone": "phone",
    "연락처": "phone",
    "전화번호": "phone",
    "exam_date": "exam_date",
    "검사일": "exam_date",
    "최근검사일": "exam_date",
    "dob": "dob",
    "생년월일": "dob",

    # ── ML 독립변수 (v2 — 병원 수집 변수 기준) ──
    # 인구통계·당뇨
    "age": "age",
    "나이": "age", "연령": "age", "만나이": "age",  # v2.2.4: 한글 '나이' 별칭(누락이었음)
    "sex": "sex",
    "DM_diagnosis_age": "dm_diagnosis_age",
    "진단나이": "dm_diagnosis_age", "진단연령": "dm_diagnosis_age",  # v2.2.4
    "dm_medication": "dm_medication",
    "당뇨약복용": "dm_medication",
    "insulin_medication": "insulin_medication",
    "인슐린투약": "insulin_medication",

    # 혈당·인슐린
    "HE_glu": "fbg",
    "공복혈당": "fbg",
    "HE_HbA1c": "hba1c",
    "당화혈색소": "hba1c",
    "HE_insulin": "he_insulin",
    "c_peptide": "c_peptide",
    "C-peptide": "c_peptide",

    # 간효소
    "HE_ast": "ast",
    "HE_alt": "alt",
    "GGT": "ggt",  # 병원 수집(참고용), 모델에 사용 안 함

    # 신장
    "HE_crea": "cr",
    "크레아티닌": "cr",

    # 지질
    "HE_chol": "total_cholesterol",
    "총콜레스테롤": "total_cholesterol",
    "HE_TG": "triglycerides",
    "중성지방": "triglycerides",
    "HE_HDL_st2": "hdl",
    "HDL": "hdl",
    "LDL": "ldl",  # 병원 실측 LDL

    # 혈압
    "SBP": "sbp",
    "수축기혈압": "sbp",
    "DBP": "dbp",
    "이완기혈압": "dbp",
    "hypertension": "hypertension",
    "고혈압": "hypertension",

    # 신체 계측
    "HE_BMI": "bmi",
    "BMI": "bmi",
    "HE_ht": "height",
    "키": "height",
    "HE_wt": "weight",
    "몸무게": "weight",

    # 소변 기본
    "HE_Upro": "he_upro",
    "요단백": "he_upro",
    "HE_Uglu": "he_uglu",
    "요당": "he_uglu",
    "HE_Ubld": "he_ubld",
    "요잠혈": "he_ubld",
    # 소변 확장
    "urine_bil": "urine_bil",
    "요빌리루빈": "urine_bil",
    "urine_uro": "urine_uro",
    "요우로빌리노겐": "urine_uro",
    "urine_ket": "urine_ket",
    "요케톤": "urine_ket",
    "urine_nit": "urine_nit",
    "요아질산염": "urine_nit",
    "urine_ph": "urine_ph",
    "요pH": "urine_ph",
    "urine_sg": "urine_sg",
    "요비중": "urine_sg",

    # 생활습관
    "smoking": "smoking",
    "흡연": "smoking",
    "drinking": "drinking",
    "음주": "drinking",
    "exercise": "exercise",
    "운동": "exercise",
    "sleep_hours": "sleep_hours",
    "수면시간": "sleep_hours",

    # 기타 (참고용)
    "visceral_fat": "visceral_fat",
    "내장지방": "visceral_fat",

    # ── v2.2.2: 병원 양식 흔한 헤더 변형 추가 ──
    # (성별/HbA1c/AST/ALT/혈압 띄어쓰기/LDL·HDL 풀네임 등 — 실제 병원 CSV 헤더)
    "성별": "sex",
    "HbA1c": "hba1c",
    "hba1c": "hba1c",
    "당화혈색소(HbA1c)": "hba1c",
    "AST": "ast",
    "ALT": "alt",
    "수축기 혈압": "sbp",
    "이완기 혈압": "dbp",
    "LDL 콜레스테롤": "ldl",
    "LDL콜레스테롤": "ldl",
    "HDL 콜레스테롤": "hdl",
    "HDL콜레스테롤": "hdl",
    "총 콜레스테롤": "total_cholesterol",
}

# v2.2.2/2.2.4: 공백·대소문자 차이를 흡수하는 정규화 매핑.
#   ("수축기 혈압"↔"수축기혈압", "HBA1C"↔"hba1c", 탭/전각공백(U+3000)/NBSP(U+00A0)/줄바꿈 제거)
_WS_DELETE = dict.fromkeys(ord(c) for c in " \t\n\r\f\v　 ")


def _norm_key(s):
    return str(s).translate(_WS_DELETE).lower()


_NORM_COLUMN_MAP = {_norm_key(k): v for k, v in CSV_COLUMN_MAP.items()}


def _lookup_db_field(csv_col):
    """원본 헤더 → DB 필드. 정확 매칭 우선, 없으면 공백류·대소문자 무시 정규화 매칭."""
    return CSV_COLUMN_MAP.get(csv_col) or _NORM_COLUMN_MAP.get(_norm_key(csv_col))


def _dedup_cols(cols):
    """중복 컬럼명을 pandas 처럼 c, c.1, c.2 로 구분 (row.get 모호성·조용한 덮어쓰기 방지)."""
    seen, out = {}, []
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c in seen:
            seen[c] += 1
            out.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def _read_excel_robust(content: bytes, string_dtypes: dict):
    """비표준 xlsx 대응 엑셀 리더.

    일부 병원/외부 프로그램이 만든 xlsx 는 styles.xml 에 name 없는 cellStyle 이 있어
    openpyxl 이 'apply_stylesheet' 에서 죽는다. calamine(Rust 기반)은 이런 파일도 읽으므로
    calamine 우선 시도 → 실패/미설치 시 openpyxl fallback. 둘 다 실패하면 예외.
    """
    # v2.2.4: 멀티시트·헤더오프셋 대응 — 전체 시트를 header 없이 str 로 읽은 뒤
    #   알려진 헤더(필수 sex/fbg/hba1c 가중)가 가장 많이 매칭되는 (시트, 헤더행)을 자동 선택.
    raw_sheets = None
    last_err = None
    for engine in ("calamine", "openpyxl"):
        try:
            raw_sheets = pd.read_excel(
                io.BytesIO(content), engine=engine, sheet_name=None, header=None, dtype=str
            )
            break
        except ImportError as e:
            last_err = e  # 엔진 미설치 → 다음 엔진
        except Exception as e:
            last_err = e  # 파싱 실패 → 다음 엔진
    if not raw_sheets:
        raise last_err or RuntimeError("엑셀 파서 없음")

    best = None  # (score, sheet, header_idx)
    for sname, raw in raw_sheets.items():
        if raw is None or raw.empty:
            continue
        for hidx in range(min(8, len(raw))):
            mapped = req = 0
            for cell in raw.iloc[hidx].tolist():
                if cell is None:
                    continue
                dbf = _lookup_db_field(str(cell).strip())
                if dbf:
                    mapped += 1
                    if dbf in ("sex", "fbg", "hba1c"):
                        req += 1
            score = mapped + req * 10  # 필수 헤더에 가중
            if score > 0 and (best is None or score > best[0]):
                best = (score, sname, hidx)

    if best is None:
        # 헤더 자동탐지 실패 → 첫 시트 1행을 헤더로 폴백
        raw = next(iter(raw_sheets.values()))
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.iloc[1:].copy()
        df.columns = _dedup_cols(raw.iloc[0].tolist())
        return df.reset_index(drop=True)

    _, sname, hidx = best
    raw = raw_sheets[sname]
    df = raw.iloc[hidx + 1:].copy()
    df.columns = _dedup_cols(raw.iloc[hidx].tolist())
    return df.reset_index(drop=True)


def _read_csv_robust(content: bytes, string_dtypes: dict):
    """CSV 다중 인코딩 대응.

    한국 병원/엑셀이 'CSV 저장' 하면 UTF-8 이 아니라 CP949(=ANSI/EUC-KR) 인 경우가 흔하다.
    UTF-8 고정으로 읽으면 한글이 깨지거나 UnicodeDecodeError 가 난다. BOM 포함 UTF-8 →
    UTF-8 → CP949 → EUC-KR 순으로 시도한다. (latin-1 은 무조건 성공하지만 한글이 깨지므로 제외)
    """
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(io.BytesIO(content), dtype=string_dtypes, encoding=enc)
            # v2.2.4: 구분자 오감지 — 단일 컬럼인데 헤더에 ;/tab/| 가 있으면 자동 구분자 추론으로 재시도
            #   (한국 엑셀 로케일이 'CSV' 를 세미콜론으로 저장하는 흔한 케이스)
            if df.shape[1] == 1 and any(d in str(df.columns[0]) for d in (";", "\t", "|")):
                df = pd.read_csv(io.BytesIO(content), dtype=string_dtypes, encoding=enc, sep=None, engine="python")
            return df
        except UnicodeDecodeError as e:
            last_err = e  # 인코딩 불일치 → 다음 인코딩
        except Exception as e:
            last_err = e  # 빈 파일/형식 오류 등은 그대로 전파(다음 인코딩도 같을 것)
            break
    raise last_err or RuntimeError("CSV 파싱 실패")


def _is_blank_cell(value) -> bool:
    """None / NaN / NaT / pd.NA 등 결측 셀을 통일 판정.
    v2.1.12 (엑셀 지원): string dtype 컬럼의 결측은 pd.NA(=float 아님)라
    기존 isinstance(float) 체크로는 못 잡혀서 헬퍼로 통일."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _parse_date(value):
    """날짜 값을 date 객체로 변환. 실패 시 None.
    엑셀은 날짜를 datetime 으로 자동 변환하므로 그 경우도 처리."""
    if _is_blank_cell(value):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        parsed = pd.to_datetime(value)
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


# 문자열 컬럼 (정규화 대상이 아님)
_STRING_FIELDS = {"name", "chart_no", "phone", "sex"}


def _sanitize_cell(s: str) -> str:
    """v2.1.9 (감사): CSV/Excel formula injection 방어.
    =,+,-,@,탭,CR 로 시작하는 셀은 앞에 ' 를 붙여 수식 실행을 막는다.
    (저장 + 추후 export 시 Excel 이 수식으로 해석하는 것 방지)"""
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def _coerce_numeric(value):
    """병원 CSV 의 흔한 비-숫자 표기들을 float 으로 정규화.

    처리하는 패턴:
      - HH:MM 시간 형식  ('7:30' → 7.5,  '8:15' → 8.25)
      - 쉼표 천 단위 구분 ('1,200' → 1200)
      - % 단위 표기       ('7.5%' → 7.5)
      - 앞뒤 공백·전각 공백
      - '-', 'N/A', 'na', '없음', '미검사', '#NULL!' → None
    실패 시 None 반환 (insert 에서 NULL 로 처리).
    """
    if _is_blank_cell(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("\u3000", "").replace(",", "")
    if not s:
        return None
    low = s.lower()
    if low in ("-", "--", "n/a", "na", "nan", "null", "#null!", "없음", "미검사", "미시행"):
        return None
    # 끝에 단위/기호 (% u/l mg/dl 등) 가 붙어있으면 제거 — 첫 비숫자 위치까지만 사용
    if s.endswith("%"):
        s = s[:-1].strip()
    # HH:MM (또는 HH:MM:SS) → 소수 시간
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [float(p) for p in parts]
            if len(nums) == 2:
                return nums[0] + nums[1] / 60.0
            if len(nums) == 3:
                return nums[0] + nums[1] / 60.0 + nums[2] / 3600.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _row_to_patient_data(row, idx: int, column_lookup: dict) -> dict:
    """CSV 한 행을 Patient 필드 dict 로 변환 (DB 접근 없음)."""
    patient_data = {}
    for csv_col, db_field in column_lookup.items():
        val = row.get(csv_col)
        if _is_blank_cell(val):
            continue
        if db_field in ("exam_date", "dob"):
            parsed = _parse_date(val)
            if parsed is not None:
                patient_data[db_field] = parsed
        elif db_field in _STRING_FIELDS:
            # 이름/차트번호/연락처/성별은 문자열 (sex 코드 변환은 아래에서)
            # v2.1.9 (감사): formula injection 방어 sanitize 적용.
            s = str(val).strip()
            if s:
                patient_data[db_field] = _sanitize_cell(s)
        else:
            # 숫자 컬럼 — HH:MM 등 비-숫자 표기 정규화
            num = _coerce_numeric(val)
            if num is not None:
                patient_data[db_field] = num

    # v2.2.4: 모든 셀이 빈 행 → ghost 환자(임상값 0) 생성 방지. None 반환 → 호출부에서 skip.
    if not patient_data:
        return None

    # 이름 기본값
    if not str(patient_data.get("name", "")).strip():
        patient_data["name"] = f"환자_{idx + 1}"

    # exam_date 기본값
    if "exam_date" not in patient_data:
        patient_data["exam_date"] = date.today()

    # sex 정규화 (단일 소스 normalize_sex): 1/2 · M/F · 남/여 · male/female 모두 처리.
    #   v2.2.6 (감사 H1): 인식 불가/결측이면 None 으로 두어 eGFR·모델이 임의 여성값을
    #   쓰지 않게 한다. (기존: 1/2 만 변환 → '남'/'male' 등이 그대로 남아 전원 여성 처리)
    if "sex" in patient_data:
        patient_data["sex"] = normalize_sex(patient_data.get("sex"))

    # ── 파생 지표 일괄 계산 (services/derived.py 의 단일 소스) ──
    # age (DOB→자동), BMI, LDL(병원 실측 우선), LDL_calc, non_HDL,
    # HE_insulin 호환값, HOMA_IR/HOMA_beta/BMI_HOMA_IR (C-peptide 기반),
    # TyG_index, eGFR, pulse_pressure, DM_duration
    patient_data = compute_derived(patient_data)

    return patient_data


@router.post("/upload/csv")
async def upload_csv(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    CSV 업로드 — 한 행 = 한 번의 검사 방문.

    처리 흐름:
      1. CSV 파싱·매핑 검증
      2. 행 → patient_data dict 변환 (DB 접근 없음)
      3. 기존 chart_no 일괄 조회
      4. 신규 환자는 생성, 기존 환자는 (exam_date) 기준으로 방문 추가
      5. 최신 방문이면 Patient row 도 최신값으로 갱신
      6. 단일 commit
      7. ML risk_level 계산은 BackgroundTasks 로 비동기 처리
    """
    # v2.1.9 (감사): 서버측 검증 — 확장자 + 크기 (프론트 검증만 믿지 않음)
    # v2.1.12: 엑셀(.xlsx) 지원 추가.
    filename = (file.filename or "").lower()
    is_csv_ext = filename.endswith(".csv")
    is_excel_ext = filename.endswith((".xlsx", ".xlsm", ".xls", ".ods"))
    # v2.2.4: 확장자 거부는 content 확인(매직바이트) 후로 미룬다 — 확장자 .csv 로 위장한 엑셀 대응.

    content = await file.read()
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB).")
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    # 차트번호/연락처/성별은 숫자로 오인되지 않게 문자열로 보존
    # (예: 차트번호 "001" 이 1.0 으로 바뀌는 것 방지). 원본 컬럼명(영문/한글) 모두 지정.
    string_dtypes = {
        "name": "string", "이름": "string",
        "chart_no": "string", "차트번호": "string",
        "phone": "string", "연락처": "string", "전화번호": "string",
        "sex": "string", "성별": "string",
    }
    # v2.2.4: 내용 기반 포맷 판별 (확장자 위장 대응).
    #   PK = xlsx/xlsm/ods(zip), D0 CF 11 E0 = 구형 .xls(OLE2 compound).
    looks_zip = content[:2] == b"PK"
    looks_ole = content[:4] == b"\xD0\xCF\x11\xE0"
    use_excel = is_excel_ext or looks_zip or looks_ole
    if not (is_csv_ext or use_excel):
        raise HTTPException(status_code=400, detail="CSV 또는 엑셀(.csv/.xlsx/.xls) 파일만 업로드 가능합니다.")
    file_label = "엑셀" if use_excel else "CSV"
    try:
        if use_excel:
            df = _read_excel_robust(content, string_dtypes)
        else:
            df = _read_csv_robust(content, string_dtypes)  # v2.2.4: 다중 인코딩(UTF-8/CP949/EUC-KR)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{file_label} 파일을 읽지 못했습니다. 파일이 손상됐거나 비표준 형식일 수 있습니다. "
                f"Excel에서 다시 저장(CSV UTF-8 또는 .xlsx)한 뒤 업로드해 주세요. "
                f"(원인: {type(e).__name__})"
            ),
        )
    MAX_ROWS = 10000
    if len(df) > MAX_ROWS:
        raise HTTPException(status_code=413, detail=f"행이 너무 많습니다 (최대 {MAX_ROWS}행).")
    # v2.2.4: 헤더만 있고 데이터가 0행이면 '성공(0건)' 으로 조용히 넘어가지 않고 명확히 안내.
    if len(df) == 0:
        raise HTTPException(status_code=400, detail="데이터 행이 없습니다. 헤더만 있거나 빈 파일입니다.")

    # ── 1) 매핑 미리보기 ─────────────────────────────────
    mapping_preview = []
    warnings = []
    errors = []
    successes = []
    column_lookup = {}  # CSV 에 실제로 존재하는 매핑 컬럼만

    for csv_col in df.columns:
        db_field = _lookup_db_field(csv_col)  # v2.2.2: 공백·대소문자 무시 매칭 포함
        if db_field:
            kind = "메타" if db_field in META_FIELDS else "변수"
            mapping_preview.append({
                "csv_column": csv_col,
                "db_field": db_field,
                "status": "mapped",
                "kind": kind,
            })
            successes.append(f"'{csv_col}' → '{db_field}' ({kind}) 매핑 성공")
            column_lookup[csv_col] = db_field
        else:
            mapping_preview.append({
                "csv_column": csv_col,
                "db_field": None,
                "status": "unmapped",
                "kind": None,
            })
            warnings.append(f"'{csv_col}' 컬럼은 매핑되지 않았습니다.")

    # ── 2) 필수 컬럼 체크 ────────────────────────────────
    # v2.2.2: 원본 헤더가 아니라 '매핑된 DB 필드' 기준으로 체크 → 헤더 변형(HbA1c/성별/띄어쓰기)도
    #   매핑만 되면 통과. (이전엔 raw 헤더 비교라 "HbA1c"(↔hba1c 대소문자)가 누락 판정됨)
    mapped_fields = set(column_lookup.values())
    required_fields = {"sex": "성별", "fbg": "공복혈당", "hba1c": "당화혈색소(HbA1c)"}
    for dbf, label in required_fields.items():
        if dbf not in mapped_fields:
            errors.append(f"필수 컬럼 누락: {label}")

    # age 없으면 dob 가 있어야 함 (둘 다 매핑 필드 기준)
    has_age = "age" in mapped_fields
    has_dob = "dob" in mapped_fields
    if not has_age and not has_dob:
        errors.append("필수 컬럼 'age' 또는 'dob' 중 하나는 있어야 합니다")

    # v2.1.9 (감사): 필수 컬럼 누락 등 errors 가 있으면 저장하지 않고 즉시 반환.
    # 이전엔 errors 를 모아두고도 저장을 계속 진행해 부분 저장 위험이 있었음.
    if errors:
        return {
            "data": {
                "file_name": file.filename,
                "total_rows": len(df),
                "created_count": 0, "updated_count": 0, "visits_added": 0,
                "skipped_count": 0, "unique_patients_affected": 0,
                "created_ids": [], "updated_ids": [], "skipped": [],
                "last_patient_id": None, "is_single_patient": False,
                "mapping_preview": mapping_preview,
                "validation": {
                    "errors": errors,
                    "warnings": warnings[:50],
                    "successes": successes,
                },
            },
            "success": False,
        }

    # ── 3) 행 변환 (DB 접근 없음) ─────────────────────────
    rows_data = []
    empty_rows = 0
    for idx, row in df.iterrows():
        try:
            pdata = _row_to_patient_data(row, idx, column_lookup)
            if pdata is None:  # v2.2.4: 빈 행 skip (ghost 환자 방지)
                empty_rows += 1
                continue
            rows_data.append((idx, pdata))
        except Exception as e:
            warnings.append(f"행 {idx + 1}: 변환 실패 - {str(e)}")
    if empty_rows:
        warnings.append(f"빈 행 {empty_rows}개를 건너뛰었습니다.")

    # ── 4) 자동 chart_no 생성 (DB count 루프 밖에서 1회) ─
    existing_total = db.query(Patient).count()
    auto_counter = existing_total
    for idx, pdata in rows_data:
        if not str(pdata.get("chart_no", "")).strip():
            auto_counter += 1
            pdata["chart_no"] = f"CN-{datetime.now().year}-{auto_counter:04d}"

    # ── 5) 기존 chart_no 일괄 조회 ───────────────────────
    chart_nos = [str(pdata["chart_no"]) for _, pdata in rows_data if pdata.get("chart_no")]
    existing_map: dict[str, Patient] = {}
    if chart_nos:
        # SQLite IN 절 한계(999) 회피 — 500개 단위로 나눠서 조회
        CHUNK = 500
        for i in range(0, len(chart_nos), CHUNK):
            batch = chart_nos[i:i + CHUNK]
            rows = db.query(Patient).filter(Patient.chart_no.in_(batch)).all()
            for p in rows:
                existing_map[p.chart_no] = p

    # 기존 환자의 이미 기록된 (patient_id, exam_date) 조합 — 완전 중복 방문 판정용
    existing_visit_keys: set[tuple[int, date]] = set()
    if existing_map:
        pid_list = [p.id for p in existing_map.values()]
        for i in range(0, len(pid_list), 500):
            batch = pid_list[i:i + 500]
            visits = db.query(MeasurementHistory.patient_id, MeasurementHistory.measured_at) \
                       .filter(MeasurementHistory.patient_id.in_(batch)).all()
            for v in visits:
                existing_visit_keys.add((v[0], v[1]))

    # ── 6) 행별 처리 ─────────────────────────────────────
    created_ids: list[int] = []           # 새로 만든 환자 id (순서 보존)
    updated_ids: list[int] = []           # 기존 환자인데 최신 방문 덮어쓴 id
    affected_ids: set[int] = set()        # 영향받은 고유 환자 id (리다이렉트 판정용)
    visits_added = 0                       # MeasurementHistory 에 새로 추가된 행 수
    skipped: list[dict] = []              # [{row, chart_no, reason}]

    # CSV 파일 내에서 같은 (chart_no, exam_date) 조합 두 번 등장 방지
    seen_in_file: set[tuple[str, date]] = set()

    # ㄴ 루프 전 정렬: 같은 chart_no 여러 행이 있을 때 exam_date 오름차순으로 처리
    #   → 최신 방문이 마지막에 반영되어 Patient.exam_date 가 가장 최신으로 남음
    def _row_sort_key(item):
        _, pdata = item
        d = pdata.get("exam_date") or date(1900, 1, 1)
        return (str(pdata.get("chart_no", "")), d)
    rows_data.sort(key=_row_sort_key)

    for idx, pdata in rows_data:
        chart_no = str(pdata.get("chart_no", "")).strip()
        exam_date_val = pdata.get("exam_date")
        if not isinstance(exam_date_val, date):
            exam_date_val = _parse_date(exam_date_val) or date.today()
            pdata["exam_date"] = exam_date_val

        # 같은 파일 안에서 (chart_no + exam_date) 중복 방지
        file_key = (chart_no, exam_date_val)
        if file_key in seen_in_file:
            skipped.append({
                "row": idx + 1, "chart_no": chart_no,
                "reason": f"파일 내 동일 방문({exam_date_val}) 중복",
            })
            continue
        seen_in_file.add(file_key)

        existing = existing_map.get(chart_no)
        try:
            if existing is None:
                # 신규 환자 + 첫 방문
                patient = Patient(**pdata)
                db.add(patient)
                db.flush()  # id 확보
                existing_map[chart_no] = patient  # 같은 파일 뒤 행들이 참조
                created_ids.append(patient.id)
                affected_ids.add(patient.id)
                _append_measurement(db, patient.id, pdata)
                visits_added += 1
                existing_visit_keys.add((patient.id, exam_date_val))
            else:
                # 기존 환자 — 같은 exam_date 방문 이미 존재하면 skip
                if (existing.id, exam_date_val) in existing_visit_keys:
                    skipped.append({
                        "row": idx + 1, "chart_no": chart_no,
                        "reason": f"동일 검사일({exam_date_val}) 데이터 이미 존재",
                    })
                    continue

                # 새 방문 → history 에 추가
                _append_measurement(db, existing.id, pdata)
                visits_added += 1
                existing_visit_keys.add((existing.id, exam_date_val))
                affected_ids.add(existing.id)

                # 최신 방문이면 Patient row 도 최신값으로 갱신 (대시보드 표시 기준)
                current_exam = existing.exam_date
                if current_exam is None or exam_date_val >= current_exam:
                    for k, v in pdata.items():
                        setattr(existing, k, v)
                    existing.risk_level = None  # 재계산 필요
                    if existing.id not in updated_ids:
                        updated_ids.append(existing.id)
                # else: 과거 방문 소급 입력 — history 에만 추가, Patient row 보존
        except Exception as e:
            warnings.append(f"행 {idx + 1} (chart_no={chart_no}): 저장 실패 - {str(e)}")

    # 단일 commit — 3000행도 수 초 내
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB 커밋 실패: {str(e)}")

    # ── 7) ML risk_level 은 백그라운드 처리 ───────────────
    pending_ids = list({*created_ids, *updated_ids})
    if pending_ids:
        background.add_task(_backfill_risk_levels_bg, pending_ids)

    # 영향받은 고유 환자 1명 → 프론트에서 대시보드로 직행
    unique_patients = len(affected_ids)
    is_single_patient = unique_patients == 1
    last_patient_id = next(iter(affected_ids)) if is_single_patient else None

    return {
        "data": {
            "file_name": file.filename,
            "total_rows": len(df),
            "created_count": len(created_ids),
            "updated_count": len(updated_ids),
            "visits_added": visits_added,
            "skipped_count": len(skipped),
            "unique_patients_affected": unique_patients,
            "created_ids": created_ids,
            "updated_ids": updated_ids,
            "skipped": skipped[:50],  # 응답 크기 제한 (최대 50개 샘플)
            "last_patient_id": last_patient_id,   # 단일 환자일 때만 id, 여러 명이면 null
            "is_single_patient": is_single_patient,
            "mapping_preview": mapping_preview,
            "validation": {
                "errors": errors,
                "warnings": warnings[:50],
                "successes": successes,
            },
        },
        "success": True,
    }


@router.get("/upload/template")
def download_template():
    """
    CSV 업로드 템플릿 다운로드 (병원 입력 스키마 v2.2).

    병원 실측값만 입력하며, age / BMI / HOMA / eGFR / LDL(미입력시) /
    dm_duration / pulse_pressure / dipstick binary 는 백엔드가 자동 계산.
    """
    columns = [
        # 메타데이터 (dob 로부터 age 자동 산출)
        "name", "chart_no", "phone", "dob", "exam_date",
        # 인구/당뇨
        "sex", "DM_diagnosis_age", "dm_medication", "insulin_medication",
        # 혈당·C-peptide
        "HE_glu", "HE_HbA1c", "c_peptide",
        # 간
        "HE_ast", "HE_alt",
        # 신장
        "HE_crea",
        # 지질 (LDL 은 병원 실측, 없으면 Friedewald fallback)
        "HE_chol", "HE_TG", "HE_HDL_st2", "LDL",
        # 혈압
        "SBP", "DBP", "hypertension",
        # 신체 (BMI 는 키·몸무게로 자동 계산)
        "HE_ht", "HE_wt",
        # 소변 기본
        "HE_Upro", "HE_Uglu", "HE_Ubld",
        # 소변 확장
        "urine_bil", "urine_uro", "urine_ket", "urine_nit", "urine_ph", "urine_sg",
        # 생활습관
        "smoking", "drinking", "exercise", "sleep_hours",
    ]
    example = [
        "김영호", "CN-2026-0001", "010-1234-5678", "1962-03-15", "2026-04-10",
        1, 52, 1, 0,
        145.0, 7.8, 2.3,
        28, 32,
        1.1,
        195, 160, 48, 115,
        135, 85, 1,
        170, 72,
        1, 1, 1,
        1, 1, 1, 0, 6.0, 1.020,
        0, 1, 1, 7.0,
    ]
    df = pd.DataFrame([example], columns=columns)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dbcare_template.csv"'},
    )
