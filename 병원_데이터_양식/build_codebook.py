"""
병원 데이터 양식 코딩북 (Codebook) 생성 스크립트
================================================
DB-care v2.2 ML 모델 입력용 변수의 정의 / 코딩 규칙 / 계산식을 CSV·Excel 로 산출.

두 섹션으로 구성:
  1) 병원 입력 변수 (raw inputs)       — 의사/간호사가 직접 기입
  2) 백엔드 자동 계산 파생 변수 (derived) — 입력된 원본값으로부터 계산

출력:
  - 병원_데이터_양식_코딩북.csv  (UTF-8-SIG, Excel 호환)
  - 병원_데이터_양식_코딩북.xlsx (서식 적용)
"""
from __future__ import annotations
import os
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH  = os.path.join(OUT_DIR, "병원_데이터_양식_코딩북.csv")
XLSX_PATH = os.path.join(OUT_DIR, "병원_데이터_양식_코딩북.xlsx")


def _safe_path(path: str) -> str:
    """기존 파일이 열려 있어 쓰기 불가하면 _v2, _v3 ... 로 백업 경로 반환."""
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


# ────────────────────────────────────────────────────────────────
# 1) 병원 입력 변수 (raw inputs) — 의사/간호사가 직접 기입
# ────────────────────────────────────────────────────────────────
RAW_INPUTS = [
    # ─ 환자정보 (메타데이터) ────────────────────────────────
    dict(no=1,  category="환자정보", column="name",               label="환자 이름",
         unit="-", dtype="문자열",
         code_values="자유 입력 (예: 김영호)",
         required="필수",
         description="환자 식별용. 보고서·대시보드 표시명."),
    dict(no=2,  category="환자정보", column="chart_no",           label="차트번호",
         unit="-", dtype="문자열",
         code_values="예: CN-2026-0001 (병원 자체 번호체계)",
         required="필수",
         description="병원 내부 고유번호. 중복 업로드 시 기준 키."),
    dict(no=3,  category="환자정보", column="phone",              label="연락처",
         unit="-", dtype="문자열",
         code_values="010-XXXX-XXXX",
         required="선택",
         description="환자 검색·연락용. ML 에 사용되지 않음."),
    dict(no=4,  category="환자정보", column="dob",                label="생년월일",
         unit="-", dtype="날짜 (YYYY-MM-DD)",
         code_values="1900-01-01 ~ 오늘",
         required="필수",
         description="만나이는 dob + exam_date 로부터 백엔드가 자동 계산 (age 입력 불필요)."),
    dict(no=5,  category="환자정보", column="exam_date",          label="검사일",
         unit="-", dtype="날짜 (YYYY-MM-DD)",
         code_values="예: 2026-04-20",
         required="필수",
         description="이 데이터가 수집·측정된 날짜. 시계열 추이 축으로 사용."),

    # ─ 인구통계 ────────────────────────────────────────────
    dict(no=6,  category="인구통계", column="sex",                label="성별",
         unit="-", dtype="코드",
         code_values="1=남성 / 2=여성  (또는 'M' / 'F')",
         required="필수",
         description="eGFR CKD-EPI 공식에 성별 보정계수 적용."),

    # ─ 당뇨 ────────────────────────────────────────────────
    dict(no=7,  category="당뇨",    column="DM_diagnosis_age",    label="당뇨 진단 나이",
         unit="세", dtype="정수",
         code_values="0 ~ 120",
         required="필수",
         description="당뇨병을 처음 진단받은 나이. DM_duration = age - DM_diagnosis_age 로 자동 파생."),
    dict(no=8,  category="당뇨",    column="dm_medication",       label="당뇨약 복용 여부",
         unit="-", dtype="코드",
         code_values="0=복용 안 함 / 1=복용 중",
         required="필수",
         description="경구 혈당강하제 복용 여부 (메트포르민 등)."),
    dict(no=9,  category="당뇨",    column="insulin_medication",  label="인슐린 투약 여부",
         unit="-", dtype="코드",
         code_values="0=투약 안 함 / 1=투약 중",
         required="필수",
         description="인슐린 주사 사용 여부."),

    # ─ 혈당 / C-peptide ────────────────────────────────────
    dict(no=10, category="혈당",    column="HE_glu",              label="공복혈당 (FPG)",
         unit="mg/dL", dtype="실수",
         code_values="40 ~ 500",
         required="필수",
         description="최소 8시간 금식 후 정맥혈당. 당뇨 진단 기준: ≥126 mg/dL."),
    dict(no=11, category="혈당",    column="HE_HbA1c",            label="당화혈색소 (HbA1c)",
         unit="%", dtype="실수",
         code_values="4.0 ~ 15.0",
         required="필수",
         description="최근 2~3개월 평균혈당 지표. 정상 ≤5.6, 전당뇨 5.7~6.4, 당뇨 ≥6.5."),
    dict(no=12, category="C-peptide", column="c_peptide",          label="C-peptide",
         unit="ng/mL", dtype="실수",
         code_values="0.1 ~ 10.0",
         required="필수",
         description="인슐린 분비능 지표 (병원 실측 원본값). "
                    "HOMA_IR·HOMA_beta·BMI_HOMA_IR 은 이 값으로 자동 계산."),

    # ─ 간효소 ──────────────────────────────────────────────
    dict(no=13, category="간효소",  column="HE_ast",              label="AST (GOT)",
         unit="U/L", dtype="실수",
         code_values="5 ~ 500",
         required="필수",
         description="아스파르테이트 아미노전달효소. 정상 ≤40."),
    dict(no=14, category="간효소",  column="HE_alt",              label="ALT (GPT)",
         unit="U/L", dtype="실수",
         code_values="5 ~ 500",
         required="필수",
         description="알라닌 아미노전달효소. 정상 ≤40."),

    # ─ 신장 ────────────────────────────────────────────────
    dict(no=15, category="신장",    column="HE_crea",             label="크레아티닌 (Cr)",
         unit="mg/dL", dtype="실수",
         code_values="0.2 ~ 10.0",
         required="필수",
         description="신기능 지표. eGFR 은 CKD-EPI 2009 공식으로 자동 계산."),

    # ─ 지질 ────────────────────────────────────────────────
    dict(no=16, category="지질",    column="HE_chol",             label="총콜레스테롤",
         unit="mg/dL", dtype="실수",
         code_values="50 ~ 500",
         required="필수",
         description="총 혈중 콜레스테롤. 정상 ≤199, 경계 200~239, 높음 ≥240."),
    dict(no=17, category="지질",    column="HE_TG",               label="중성지방 (TG)",
         unit="mg/dL", dtype="실수",
         code_values="20 ~ 1500",
         required="필수",
         description="트리글리세라이드. 정상 <150."),
    dict(no=18, category="지질",    column="HE_HDL_st2",          label="HDL 콜레스테롤",
         unit="mg/dL", dtype="실수",
         code_values="10 ~ 150",
         required="필수",
         description="고밀도 지단백. 낮을수록 심혈관 위험 ↑."),
    dict(no=19, category="지질",    column="LDL",                 label="LDL 콜레스테롤",
         unit="mg/dL", dtype="실수",
         code_values="10 ~ 300",
         required="필수",
         description="저밀도 지단백 (병원 실측치 우선). "
                    "미입력 시 Friedewald 공식으로 자동 계산 (TG < 400 한정)."),

    # ─ 혈압 ────────────────────────────────────────────────
    dict(no=20, category="혈압",    column="SBP",                 label="수축기 혈압",
         unit="mmHg", dtype="정수",
         code_values="70 ~ 250",
         required="필수",
         description="2·3회 측정 평균값 사용. pulse_pressure·hypertension 은 자동 파생."),
    dict(no=21, category="혈압",    column="DBP",                 label="이완기 혈압",
         unit="mmHg", dtype="정수",
         code_values="40 ~ 150",
         required="필수",
         description="2·3회 측정 평균값 사용."),

    # ─ 신체 계측 ──────────────────────────────────────────
    dict(no=22, category="신체계측", column="HE_ht",              label="키",
         unit="cm", dtype="실수",
         code_values="100 ~ 220",
         required="필수",
         description="BMI = weight / (height/100)² 로 자동 계산."),
    dict(no=24, category="신체계측", column="HE_wt",              label="몸무게",
         unit="kg", dtype="실수",
         code_values="20 ~ 200",
         required="필수",
         description=""),

    # ─ 소변 dipstick (원시값) ─────────────────────────────
    dict(no=25, category="소변",    column="HE_Upro",             label="요단백",
         unit="-", dtype="코드",
         code_values="1=음성 / 2=± / 3=1+ / 4=2+ / 5=3+ / 6=4+",
         required="필수",
         description="dipstick 원시값. 시스템이 ≥2 양성 binary (HE_Upro_pos) 로 자동 파생."),
    dict(no=26, category="소변",    column="HE_Uglu",             label="요당",
         unit="-", dtype="코드",
         code_values="1=음성 / 2=± / 3=1+ / 4=2+ / 5=3+ / 6=4+",
         required="필수",
         description="≥2 양성 binary (HE_Uglu_pos) 자동 파생."),
    dict(no=27, category="소변",    column="HE_Ubld",             label="요잠혈",
         unit="-", dtype="코드",
         code_values="1=음성 / 2=± / 3=1+ / 4=2+ / 5=3+ / 6=4+",
         required="필수",
         description="≥2 양성 binary (HE_Ubld_pos) 자동 파생."),
    dict(no=28, category="소변",    column="urine_bil",           label="요빌리루빈",
         unit="-", dtype="코드",
         code_values="1=음성 / 2=± / 3=1+ / 4=2+ / 5=3+",
         required="필수",
         description="≥2 양성 binary (HE_Ubil_pos) 자동 파생."),
    dict(no=29, category="소변",    column="urine_uro",           label="요우로빌리노겐",
         unit="-", dtype="코드",
         code_values="1=정상 / 2=± / 3=1+ / 4=2+ / 5=3+",
         required="필수",
         description="≥2 비정상 binary (HE_Uro_abn) 자동 파생."),
    dict(no=30, category="소변",    column="urine_ket",           label="요케톤",
         unit="-", dtype="코드",
         code_values="1=음성 / 2=± / 3=1+ / 4=2+ / 5=3+",
         required="필수",
         description="≥2 양성 binary (HE_Uket_pos) 자동 파생."),
    dict(no=31, category="소변",    column="urine_nit",           label="요아질산염",
         unit="-", dtype="코드",
         code_values="0=음성 / 1=양성",
         required="필수",
         description="요로감염 간접 지표."),
    dict(no=32, category="소변",    column="urine_ph",            label="요 pH",
         unit="-", dtype="실수",
         code_values="4.5 ~ 9.0",
         required="필수",
         description="실측값 그대로 입력."),
    dict(no=33, category="소변",    column="urine_sg",            label="요비중 (Specific Gravity)",
         unit="-", dtype="실수",
         code_values="1.000 ~ 1.040",
         required="필수",
         description="신장의 요 농축능 지표. 실측값 그대로 입력."),

    # ─ 생활습관 ───────────────────────────────────────────
    dict(no=34, category="생활습관", column="smoking",            label="흡연",
         unit="-", dtype="코드",
         code_values="0=비흡연 / 1=흡연 중",
         required="필수",
         description="현재 흡연 여부 (과거 흡연은 0 처리)."),
    dict(no=35, category="생활습관", column="drinking",           label="음주 (최근 1개월)",
         unit="-", dtype="코드",
         code_values="0=없음 / 1=있음",
         required="필수",
         description="최근 한 달 음주 경험 여부."),
    dict(no=36, category="생활습관", column="exercise",           label="규칙적 유산소 운동",
         unit="-", dtype="코드",
         code_values="0=안 함 / 1=주 150분 이상",
         required="필수",
         description="중강도 유산소 운동 주 150분 이상 또는 고강도 75분 이상 여부."),
    dict(no=37, category="생활습관", column="sleep_hours",        label="일평균 수면시간",
         unit="시간", dtype="실수",
         code_values="0 ~ 14",
         required="필수",
         description="평균 수면시간. sleep_7h binary (≥7시간 양호) 로 자동 파생."),
]


# ────────────────────────────────────────────────────────────────
# 2) 백엔드 자동 계산 파생 변수 (derived) — ML 모델 입력
# ────────────────────────────────────────────────────────────────
DERIVED_VARS = [
    dict(no=38, category="자동계산", column="age",              label="만 나이",
         unit="세", dtype="정수",
         code_values="0 ~ 120",
         required="자동",
         description="계산식: (exam_date - dob) // 365.25. 병원 입력 불필요."),
    dict(no=39, category="자동계산", column="bmi",              label="체질량지수 (BMI)",
         unit="kg/m²", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: weight / (height/100)². 정상 ≤22.9, 과체중 23~24.9, 비만 ≥25."),
    dict(no=40, category="자동계산", column="ldl_calc",         label="LDL (Friedewald 계산)",
         unit="mg/dL", dtype="실수",
         code_values="계산 결과 (TG < 400 에서만)",
         required="자동",
         description="계산식: HE_chol - HE_HDL_st2 - HE_TG/5. "
                    "병원 LDL 실측치가 있으면 ldl 컬럼 그대로 사용, ldl_calc 는 참고값."),
    dict(no=41, category="자동계산", column="non_hdl",          label="non-HDL 콜레스테롤",
         unit="mg/dL", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: HE_chol - HE_HDL_st2."),
    dict(no=42, category="자동계산", column="egfr",             label="추정 사구체여과율 (eGFR)",
         unit="mL/min/1.73m²", dtype="실수",
         code_values="CKD-EPI 2009 공식",
         required="자동",
         description="계산식: 141 × min(Cr/κ,1)^α × max(Cr/κ,1)^-1.209 × 0.993^age × (1.018 여성) / "
                    "κ=0.9(남)/0.7(여), α=-0.411(남)/-0.329(여)."),
    dict(no=43, category="자동계산", column="he_insulin",       label="HE_insulin (하위호환)",
         unit="µU/mL", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: c_peptide × 3.0. "
                    "v2.2 모델은 C-peptide 단위로 학습됐으므로 내부 ML 에 사용되지 않음. "
                    "구 UI·CSV 호환용으로만 저장."),
    dict(no=44, category="자동계산", column="homa_ir",          label="HOMA-IR (인슐린저항성)",
         unit="-", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: HE_glu × C_peptide / 405  (v2.2 C-peptide 기반). "
                    "값이 클수록 인슐린저항성 심함."),
    dict(no=45, category="자동계산", column="homa_beta",        label="HOMA-β (베타세포 기능)",
         unit="-", dtype="실수",
         code_values="계산 결과 (glu > 63 에서만)",
         required="자동",
         description="계산식: 360 × C_peptide / (HE_glu - 63). "
                    "값이 작을수록 췌장 베타세포 기능 저하."),
    dict(no=46, category="자동계산", column="bmi_homa_ir",      label="BMI × HOMA-IR",
         unit="-", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: BMI × HOMA_IR. 비만 동반 인슐린저항성 지표."),
    dict(no=47, category="자동계산", column="tyg_index",        label="TyG index",
         unit="-", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: ln(HE_TG × HE_glu / 2). 인슐린저항성 간접 지표 (C-peptide 없을 때 보완)."),
    dict(no=48, category="자동계산", column="pulse_pressure",   label="맥압",
         unit="mmHg", dtype="실수",
         code_values="계산 결과",
         required="자동",
         description="계산식: SBP - DBP. 값이 클수록 동맥경직도 심함."),
    dict(no=49, category="자동계산", column="hypertension",     label="고혈압 여부",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="계산식: 1 if (SBP ≥ 140 or DBP ≥ 90) else 0  "
                    "(대한고혈압학회 기준). 병원이 명시적으로 값을 입력한 경우 그 값을 존중."),
    dict(no=49, category="자동계산", column="dm_duration",      label="당뇨 이환기간",
         unit="년", dtype="정수",
         code_values="0 ~ 120",
         required="자동",
         description="계산식: age - DM_diagnosis_age."),
    dict(no=50, category="자동계산", column="HE_Upro_pos",      label="요단백 양성",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="HE_Upro ≥ 2 이면 1 (양성), 아니면 0."),
    dict(no=51, category="자동계산", column="HE_Uglu_pos",      label="요당 양성",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="HE_Uglu ≥ 2 이면 1, 아니면 0."),
    dict(no=52, category="자동계산", column="HE_Ubld_pos",      label="요잠혈 양성",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="HE_Ubld ≥ 2 이면 1, 아니면 0."),
    dict(no=53, category="자동계산", column="HE_Ubil_pos",      label="요빌리루빈 양성",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="urine_bil ≥ 2 이면 1, 아니면 0."),
    dict(no=54, category="자동계산", column="HE_Uket_pos",      label="요케톤 양성",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="urine_ket ≥ 2 이면 1, 아니면 0."),
    dict(no=55, category="자동계산", column="HE_Uro_abn",       label="요우로빌리노겐 비정상",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="urine_uro ≥ 2 이면 1, 아니면 0."),
    dict(no=56, category="자동계산", column="HE_Unitr_b",       label="요아질산염 binary",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="urine_nit 값 그대로 (0/1) 저장."),
    dict(no=57, category="자동계산", column="sleep_7h",         label="충분수면 여부",
         unit="-", dtype="binary",
         code_values="0 / 1",
         required="자동",
         description="sleep_hours ≥ 7 이면 1, 아니면 0."),
]


# ────────────────────────────────────────────────────────────────
# 결합 → DataFrame
# ────────────────────────────────────────────────────────────────
all_rows = RAW_INPUTS + DERIVED_VARS
# 자동 번호 재부여 (수동 no 값 무시) — 항상 1..N 순차
for i, row in enumerate(all_rows, start=1):
    row["no"] = i

COLUMNS = ["no", "category", "column", "label", "unit", "dtype",
           "code_values", "required", "description"]
COL_LABELS_KR = {
    "no":          "번호",
    "category":    "카테고리",
    "column":      "변수명",
    "label":       "한글명",
    "unit":        "단위",
    "dtype":       "데이터 타입",
    "code_values": "값/코드 범위",
    "required":    "필수 여부",
    "description": "설명 / 계산식",
}

df = pd.DataFrame(all_rows, columns=COLUMNS)
df_kr = df.rename(columns=COL_LABELS_KR)


# ────────────────────────────────────────────────────────────────
# CSV 저장 (UTF-8-SIG → Excel 에서 한글 정상 표시)
# ────────────────────────────────────────────────────────────────
CSV_PATH = _safe_path(CSV_PATH)
df_kr.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
print(f"[OK] CSV 저장: {CSV_PATH}")


# ────────────────────────────────────────────────────────────────
# Excel 저장 (서식 적용)
# ────────────────────────────────────────────────────────────────
XLSX_PATH = _safe_path(XLSX_PATH)
with pd.ExcelWriter(XLSX_PATH, engine="openpyxl") as writer:
    df_kr.to_excel(writer, sheet_name="코딩북", index=False)

    wb = writer.book
    ws = wb["코딩북"]

    # 헤더 스타일
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="4F46E5")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(border_style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    # 컬럼 너비 자동 조정
    col_widths = {
        "번호": 6, "카테고리": 12, "변수명": 22, "한글명": 22,
        "단위": 12, "데이터 타입": 14, "값/코드 범위": 40,
        "필수 여부": 10, "설명 / 계산식": 60,
    }
    for col_idx, col_name in enumerate(df_kr.columns, start=1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = col_widths.get(col_name, 15)

    # 카테고리별 배경색 구분
    cat_colors = {
        "환자정보":  "FEF3C7",   # amber-50
        "인구통계":  "FEF3C7",
        "당뇨":      "DBEAFE",   # blue-50
        "혈당":      "DBEAFE",
        "C-peptide": "DBEAFE",
        "간효소":    "F3E8FF",   # purple-50
        "신장":      "F3E8FF",
        "지질":      "F3E8FF",
        "혈압":      "FCE7F3",   # pink-50
        "신체계측":  "FCE7F3",
        "소변":      "E0F2FE",   # sky-50
        "생활습관":  "DCFCE7",   # green-50
        "자동계산":  "F3F4F6",   # gray-100
    }

    cat_col_idx = df_kr.columns.get_loc("카테고리") + 1
    for r in range(2, ws.max_row + 1):
        cat = ws.cell(row=r, column=cat_col_idx).value
        fill_color = cat_colors.get(cat, "FFFFFF")
        fill = PatternFill("solid", fgColor=fill_color)
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = border
            cell.alignment = Alignment(
                horizontal="center" if c in (1, 2, 5, 6, 8) else "left",
                vertical="center",
                wrap_text=True,
            )
            if fill_color != "FFFFFF":
                cell.fill = fill

    # 필수/자동 열 강조
    req_col_idx = df_kr.columns.get_loc("필수 여부") + 1
    red_font = Font(bold=True, color="DC2626")
    gray_font = Font(color="6B7280", italic=True)
    for r in range(2, ws.max_row + 1):
        cell = ws.cell(row=r, column=req_col_idx)
        if cell.value == "필수":
            cell.font = red_font
        elif cell.value == "자동":
            cell.font = gray_font

    ws.freeze_panes = "A2"

print(f"[OK] Excel 저장: {XLSX_PATH}")
print(f"\n총 변수: {len(all_rows)}개")
print(f"  병원 입력 (raw):    {len(RAW_INPUTS)}개")
print(f"  자동 계산 (derived): {len(DERIVED_VARS)}개")
