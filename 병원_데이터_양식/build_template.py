"""
병원 데이터 수집 Excel 템플릿 생성 스크립트 (v2.2)
===========================================
DB-care v2.2 ML 모델 입력용 Raw Data 양식.

병원은 **실측 원본값만** 입력하고, 파생/계산 지표는 백엔드가 자동으로 계산합니다.

병원 입력 (원본 측정값):
  - 환자정보 (생년월일 필수, 나이는 자동 계산),
  - 당뇨·혈당 (FPG/HbA1c/C-peptide),
  - 간 (AST/ALT),
  - 신장 (Cr),
  - 지질 (총콜/TG/HDL/LDL — 병원 실측),
  - 혈압 (SBP/DBP),
  - 신체 (키/몸무게),
  - 소변 dipstick,
  - 생활습관

백엔드 자동 계산 (입력 불필요):
  - age            = (exam_date - dob) // 365.25     ← 생년월일로부터 자동 계산
  - BMI            = weight / (height/100)²
  - non_HDL        = chol - HDL
  - LDL_calc       = chol - HDL - TG/5  (Friedewald) ← LDL 미입력 시 fallback
  - eGFR           = CKD-EPI(Cr, age, sex)
  - hypertension   = 1 if (SBP ≥ 140 or DBP ≥ 90) else 0   (KSH 기준)
  - HOMA_IR        = glu × C-peptide / 405            (v2.2 C-peptide 기반)
  - HOMA_beta      = 360 × C-peptide / (glu - 63)     (v2.2 C-peptide 기반)
  - BMI_HOMA_IR    = BMI × HOMA_IR
  - TyG_index      = ln(TG × glu / 2)
  - DM_duration    = age - DM_diagnosis_age
  - pulse_pressure = SBP - DBP
  - dipstick 양성 binary (HE_Upro_pos 등)
  - sleep_7h       = sleep_hours ≥ 7

출력:
  - 병원_데이터_양식.xlsx : 3개 시트 (입력양식 / 변수정의서 / 예시데이터)
  - 병원_데이터_양식.csv : UTF-8-SIG CSV
"""
from __future__ import annotations
import os
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(OUT_DIR, "병원_데이터_양식.xlsx")
CSV_PATH  = os.path.join(OUT_DIR, "병원_데이터_양식.csv")


def _safe_path(path: str) -> str:
    """기존 파일이 Excel 등에 열려 쓰기 불가하면 _v2, _v3 ... 로 백업 경로 반환."""
    if not os.path.exists(path):
        return path
    try:
        with open(path, "ab"):
            pass
        return path
    except PermissionError:
        base, ext = os.path.splitext(path)
        i = 2
        while True:
            alt = f"{base}_v{i}{ext}"
            if not os.path.exists(alt):
                return alt
            i += 1

# ──────────────────────────────────────────────────────────────
# 변수 정의서
#   category : 상위 분류
#   column   : CSV/Excel 컬럼명 (영문) — 시스템 필드명과 일치
#   label    : 한국어 라벨
#   unit     : 단위
#   dtype    : 입력 형식
#   code     : 코드값 / 범위
#   required : 필수 여부
#   note     : 비고 (검사 방법, KNHANES 매칭 등)
# ──────────────────────────────────────────────────────────────
VARIABLES = [
    # ── 메타데이터 ──────────────────────────────────────────
    dict(category="환자정보", column="name",         label="환자 이름",     unit="-",        dtype="문자",    code="",                             required=True,  note="필수"),
    dict(category="환자정보", column="chart_no",     label="차트번호",      unit="-",        dtype="문자",    code="예) CN-2026-0001",              required=True,  note="병원 내부 고유번호"),
    dict(category="환자정보", column="phone",        label="연락처",        unit="-",        dtype="문자",    code="010-XXXX-XXXX",                required=False, note="선택"),
    dict(category="환자정보", column="dob",          label="생년월일",      unit="-",        dtype="날짜",    code="YYYY-MM-DD",                   required=True,  note="예) 1962-03-15 — 나이는 백엔드가 dob·exam_date 로부터 자동 계산"),
    dict(category="환자정보", column="exam_date",    label="검사일",        unit="-",        dtype="날짜",    code="YYYY-MM-DD",                   required=True,  note="이 검사가 이루어진 날짜"),

    # ── 인구/당뇨 ──────────────────────────────────────────
    dict(category="인구통계", column="sex",                label="성별",               unit="-",      dtype="코드",    code="1=남, 2=여 (또는 M/F)",           required=True,  note=""),
    dict(category="당뇨",    column="DM_diagnosis_age",   label="당뇨 진단 나이",       unit="세",      dtype="정수",    code="0-120",                         required=True,  note="DM_duration = age - DM_diagnosis_age 로 자동 계산"),
    dict(category="당뇨",    column="dm_medication",      label="당뇨약 복용 여부",     unit="-",      dtype="코드",    code="0=복용안함, 1=복용",              required=True,  note="경구 혈당강하제"),
    dict(category="당뇨",    column="insulin_medication", label="인슐린 투약 여부",     unit="-",      dtype="코드",    code="0=투약안함, 1=투약",              required=True,  note=""),

    # ── 혈당 / 인슐린 ─────────────────────────────────────
    dict(category="혈당",    column="HE_glu",      label="공복혈당 (FPG)",       unit="mg/dL",   dtype="실수",    code="40-500",                         required=True,  note=""),
    dict(category="혈당",    column="HE_HbA1c",    label="당화혈색소 (HbA1c)",   unit="%",       dtype="실수",    code="4.0-15.0",                      required=True,  note=""),
    dict(category="인슐린",  column="c_peptide",   label="C-peptide",            unit="ng/mL",   dtype="실수",    code="0.1-10.0",                      required=True,  note="insulin·HOMA 지수·TyG 지수는 백엔드가 자동 계산"),

    # ── 간 ────────────────────────────────────────────────
    dict(category="간효소",  column="HE_ast",  label="AST (GOT)",  unit="U/L",   dtype="실수", code="5-500",  required=True,  note="정상 ≤40"),
    dict(category="간효소",  column="HE_alt",  label="ALT (GPT)",  unit="U/L",   dtype="실수", code="5-500",  required=True,  note="정상 ≤40"),

    # ── 신장 ─────────────────────────────────────────────
    dict(category="신장",    column="HE_crea", label="크레아티닌 (Cr)", unit="mg/dL", dtype="실수", code="0.2-10.0", required=True, note="eGFR 은 백엔드가 CKD-EPI 공식으로 자동 계산"),

    # ── 지질 ─────────────────────────────────────────────
    dict(category="지질",    column="HE_chol",    label="총콜레스테롤",       unit="mg/dL", dtype="실수", code="50-500",  required=True,  note=""),
    dict(category="지질",    column="HE_TG",      label="중성지방 (TG)",       unit="mg/dL", dtype="실수", code="20-1500", required=True,  note=""),
    dict(category="지질",    column="HE_HDL_st2", label="HDL 콜레스테롤",     unit="mg/dL", dtype="실수", code="10-150",  required=True,  note=""),
    dict(category="지질",    column="LDL",        label="LDL 콜레스테롤",     unit="mg/dL", dtype="실수", code="10-300",  required=True,  note="병원 실측치. 미입력 시 Friedewald 식으로 자동 계산 (non-HDL 은 자동 계산)"),

    # ── 혈압 ──────────────────────────────────────────────
    dict(category="혈압",    column="SBP",          label="수축기 혈압",          unit="mmHg", dtype="정수", code="70-250",                            required=True, note="2,3회 평균. 맥압·고혈압 여부는 자동 계산"),
    dict(category="혈압",    column="DBP",          label="이완기 혈압",          unit="mmHg", dtype="정수", code="40-150",                            required=True, note="2,3회 평균"),

    # ── 신체 계측 ────────────────────────────────────────
    dict(category="신체계측", column="HE_ht",        label="키",                   unit="cm",    dtype="실수", code="100-220", required=True,  note="BMI 는 키·몸무게로 자동 계산"),
    dict(category="신체계측", column="HE_wt",        label="몸무게",               unit="kg",    dtype="실수", code="20-200", required=True,  note=""),

    # ── 소변 dipstick ─────────────────────────────────────
    dict(category="소변", column="HE_Upro",   label="요단백",         unit="-", dtype="코드", code="1=음성, 2=±, 3=1+, 4=2+, 5=3+, 6=4+", required=True,  note="dipstick 원시값 (시스템이 ≥2 양성 처리)"),
    dict(category="소변", column="HE_Uglu",   label="요당",           unit="-", dtype="코드", code="1=음성, 2=±, 3=1+, 4=2+, 5=3+, 6=4+", required=True,  note=""),
    dict(category="소변", column="HE_Ubld",   label="요잠혈",         unit="-", dtype="코드", code="1=음성, 2=±, 3=1+, 4=2+, 5=3+, 6=4+", required=True,  note=""),
    dict(category="소변", column="urine_bil", label="요빌리루빈",     unit="-", dtype="코드", code="1=음성, 2=±, 3=1+, 4=2+, 5=3+",       required=True,  note=""),
    dict(category="소변", column="urine_uro", label="요우로빌리노겐", unit="-", dtype="코드", code="1=정상, 2=±, 3=1+, 4=2+, 5=3+",      required=True,  note="≥2 = 비정상"),
    dict(category="소변", column="urine_ket", label="요케톤",         unit="-", dtype="코드", code="1=음성, 2=±, 3=1+, 4=2+, 5=3+",       required=True,  note=""),
    dict(category="소변", column="urine_nit", label="요아질산염",     unit="-", dtype="코드", code="0=음성, 1=양성",                       required=True,  note=""),
    dict(category="소변", column="urine_ph",  label="요 pH",          unit="-", dtype="실수", code="4.5-9.0",                              required=True,  note="실측값"),
    dict(category="소변", column="urine_sg",  label="요비중 (Specific Gravity)", unit="-", dtype="실수", code="1.000-1.040",              required=True,  note="실측값"),

    # ── 생활습관 ────────────────────────────────────────
    dict(category="생활습관", column="smoking",     label="흡연",                   unit="-",   dtype="코드", code="0=비흡연, 1=흡연 중",           required=True, note=""),
    dict(category="생활습관", column="drinking",    label="음주 (최근 1개월)",      unit="-",   dtype="코드", code="0=없음, 1=있음",               required=True, note=""),
    dict(category="생활습관", column="exercise",    label="규칙적 유산소 운동",     unit="-",   dtype="코드", code="0=안함, 1=주 150분 이상",      required=True, note=""),
    dict(category="생활습관", column="sleep_hours", label="일평균 수면시간",        unit="시간", dtype="실수", code="0-14",                          required=True, note="시스템이 ≥7시간 binary 로 자동 파생"),
]

df_vars = pd.DataFrame(VARIABLES)
df_vars.index = range(1, len(df_vars) + 1)
df_vars.index.name = "No"

# ──────────────────────────────────────────────────────────────
# 입력양식 (빈 템플릿) — 헤더만 있고 데이터 비어있음
# ──────────────────────────────────────────────────────────────
columns_in_order = df_vars["column"].tolist()
df_template = pd.DataFrame(columns=columns_in_order)

# ──────────────────────────────────────────────────────────────
# 예시데이터 (샘플 3명)
# ──────────────────────────────────────────────────────────────
examples = [
    # 환자 1 — 고위험 (장기 당뇨, 혈당 컨트롤 안 됨)
    dict(name="김영호", chart_no="CN-2026-0001", phone="010-1111-2222", dob="1960-05-12", exam_date="2026-04-20",
         sex=1, DM_diagnosis_age=48, dm_medication=1, insulin_medication=1,
         HE_glu=168, HE_HbA1c=8.4, c_peptide=1.8,
         HE_ast=35, HE_alt=42,
         HE_crea=1.35,
         HE_chol=210, HE_TG=220, HE_HDL_st2=38, LDL=128,
         SBP=148, DBP=92,
         HE_ht=168, HE_wt=78.5,
         HE_Upro=3, HE_Uglu=4, HE_Ubld=1, urine_bil=1, urine_uro=1, urine_ket=1, urine_nit=0,
         urine_ph=5.5, urine_sg=1.020,
         smoking=1, drinking=1, exercise=0, sleep_hours=5.5),

    # 환자 2 — 중위험 (관리 중, 경계)
    dict(name="이수민", chart_no="CN-2026-0002", phone="010-3333-4444", dob="1968-11-08", exam_date="2026-04-20",
         sex=2, DM_diagnosis_age=51, dm_medication=1, insulin_medication=0,
         HE_glu=132, HE_HbA1c=7.1, c_peptide=2.6,
         HE_ast=26, HE_alt=28,
         HE_crea=0.85,
         HE_chol=192, HE_TG=158, HE_HDL_st2=52, LDL=108,
         SBP=128, DBP=82,
         HE_ht=160, HE_wt=62,
         HE_Upro=1, HE_Uglu=1, HE_Ubld=1, urine_bil=1, urine_uro=1, urine_ket=1, urine_nit=0,
         urine_ph=6.0, urine_sg=1.018,
         smoking=0, drinking=0, exercise=1, sleep_hours=7.0),

    # 환자 3 — 저위험 (양호)
    dict(name="박준서", chart_no="CN-2026-0003", phone="010-5555-6666", dob="1975-02-22", exam_date="2026-04-20",
         sex=1, DM_diagnosis_age=48, dm_medication=1, insulin_medication=0,
         HE_glu=118, HE_HbA1c=6.5, c_peptide=3.1,
         HE_ast=22, HE_alt=25,
         HE_crea=0.95,
         HE_chol=182, HE_TG=120, HE_HDL_st2=58, LDL=100,
         SBP=120, DBP=76,
         HE_ht=172, HE_wt=67.5,
         HE_Upro=1, HE_Uglu=1, HE_Ubld=1, urine_bil=1, urine_uro=1, urine_ket=1, urine_nit=0,
         urine_ph=6.5, urine_sg=1.015,
         smoking=0, drinking=0, exercise=1, sleep_hours=7.5),
]
df_example = pd.DataFrame(examples, columns=columns_in_order)

# ──────────────────────────────────────────────────────────────
# Excel 저장 + 서식
# ──────────────────────────────────────────────────────────────
XLSX_PATH = _safe_path(XLSX_PATH)
with pd.ExcelWriter(XLSX_PATH, engine="openpyxl") as writer:
    df_template.to_excel(writer, sheet_name="입력양식", index=False)
    df_vars.to_excel(writer,     sheet_name="변수정의서")
    df_example.to_excel(writer,  sheet_name="예시데이터", index=False)

    wb = writer.book

    # 헤더 스타일 공통
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="4F46E5")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(border_style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for sheet_name in ["입력양식", "변수정의서", "예시데이터"]:
        ws = wb[sheet_name]
        # 헤더 행
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border

        # 컬럼 너비 자동
        for col_idx, col_cells in enumerate(ws.columns, start=1):
            max_len = 0
            for c in col_cells:
                v = c.value
                if v is None:
                    continue
                length = sum(2 if ord(ch) > 127 else 1 for ch in str(v))
                max_len = max(max_len, length)
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 10), 45)

        # 데이터 행 테두리
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)

        ws.freeze_panes = "A2"

    # 변수정의서의 "required" 열 — 필수는 빨강 강조
    ws_def = wb["변수정의서"]
    headers = [c.value for c in ws_def[1]]
    if "required" in headers:
        col_idx = headers.index("required") + 1
        red_font = Font(bold=True, color="DC2626")
        for r in range(2, ws_def.max_row + 1):
            cell = ws_def.cell(row=r, column=col_idx)
            if cell.value is True:
                cell.value = "필수"
                cell.font = red_font
                cell.alignment = Alignment(horizontal="center")
            elif cell.value is False:
                cell.value = "선택"
                cell.alignment = Alignment(horizontal="center")

print(f"[OK] Excel 저장: {XLSX_PATH}")

# ──────────────────────────────────────────────────────────────
# CSV 저장 (예시데이터 포함, UTF-8-SIG for Excel 한글 호환)
# ──────────────────────────────────────────────────────────────
CSV_PATH = _safe_path(CSV_PATH)
df_example.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
print(f"[OK] CSV 저장: {CSV_PATH}")
print(f"\n총 변수: {len(VARIABLES)}개")
print(f"  필수: {sum(1 for v in VARIABLES if v['required'])}개")
print(f"  선택: {sum(1 for v in VARIABLES if not v['required'])}개")
