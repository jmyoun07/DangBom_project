"""병원 배포용 졸업자 RAW 데이터셋 템플릿 + 코딩북 생성 (롱포맷).

★ 롱포맷을 쓰는 이유
  합병증 위험도(전/후)는 병원이 입력하는 값이 아니라, 각 방문의 검사수치를 ML 모델에
  넣어 자동 산출한다(services/graduates.py::_predict_comp). 따라서 초진·졸업 각 시점의
  검사수치가 한 행씩 들어와야 '치료 전 → 후' 합병증 변화를 보여줄 수 있다.
  (기존 wide 양식은 HbA1c 전/후만 있어 합병증 막대가 비어 있었다.)

시트 3개:
  1) '데이터'   — 병원이 채우는 시트 (환자 1명 = 2행: 초진/졸업)
  2) '코딩북'   — 컬럼별 코드값·형식·필수여부
  3) '작성방법' — 사용법·주의사항·자주 하는 실수

실행: python scripts/make_graduate_raw_template.py
"""
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent.parent / "졸업자_RAW_데이터셋_양식_병원발송용.xlsx"

# ── 컬럼: backend 파서/모델이 인식하는 이름과 정확히 일치해야 함 ──────────
COLUMNS = [
    # 식별·방문
    "chart_no", "name", "sex", "dob", "visit_type", "visit_date",
    # 당뇨 이력
    "dm_diagnosis_age", "dm_duration_months", "treatment_months",
    "dm_medication", "dm_med_count", "insulin_medication",
    # 혈당 (필수)
    "hba1c", "fbg", "c_peptide",
    # 지질 (필수)
    "total_cholesterol", "triglycerides", "hdl", "ldl",
    # 신장 (필수)
    "cr",
    # 혈압 (필수)
    "sbp", "dbp",
    # 신체 (필수)
    "height", "weight",
    # 간효소
    "ast", "alt", "ggt",
    # 소변 dipstick
    "he_upro", "he_uglu", "he_ubld", "urine_bil", "urine_uro", "urine_ket",
    "urine_nit", "urine_ph", "urine_sg",
    # 생활습관
    "smoking", "drinking", "exercise", "sleep_hours",
]

# 필수(없으면 합병증 위험도 산출 불가) — REQUIRED_CLINICAL_FIELDS 기준
REQUIRED = {"sex", "hba1c", "fbg", "c_peptide", "total_cholesterol",
            "triglycerides", "hdl", "cr", "sbp", "dbp", "height", "weight"}
KEY_COLS = {"chart_no", "name", "visit_type", "visit_date", "dob"}

# ── 예시 데이터: 환자 3명 × 2행(초진/졸업) ─────────────────────────────
ROWS = [
    # 1. 김영수 — 전형적 개선 사례 (모든 항목 채움)
    ["D1234", "김영수", "남", "1968-03-15", "초진", "2025-01-10",
     52, 72, 6, 1, 2, 0,
     8.7, 168, 0.87, 205, 210, 41, 122,
     1.12, 142, 88, 172, 78,
     38, 45, 62,
     2, 3, 1, 1, 2, 1, 0, 5.5, 1.020,
     0, 1, 1, 6.5],
    ["D1234", "김영수", "남", "1968-03-15", "졸업", "2025-07-14",
     52, 78, 6, 1, 1, 0,
     6.1, 104, 1.62, 178, 132, 48, 104,
     0.98, 124, 76, 172, 74,
     28, 30, 41,
     1, 1, 1, 1, 2, 1, 0, 6.0, 1.015,
     0, 1, 2, 7.0],
    # 2. 이정미 — 신장 기능 회복 사례 (Cr 개선 → eGFR 자동 상승)
    ["D2345", "이정미", "여", "1962-11-02", "초진", "2025-02-20",
     58, 96, 9, 1, 3, 0,
     9.4, 192, 0.68, 224, 268, 38, 132,
     1.38, 156, 94, 158, 68,
     42, 51, 78,
     3, 3, 2, 1, 2, 1, 0, 5.0, 1.025,
     0, 0, 0, 5.5],
    ["D2345", "이정미", "여", "1962-11-02", "졸업", "2025-11-18",
     58, 105, 9, 1, 1, 0,
     6.4, 108, 1.44, 182, 140, 52, 102,
     1.02, 128, 78, 158, 63,
     30, 33, 44,
     1, 1, 1, 1, 2, 1, 0, 6.0, 1.018,
     0, 0, 2, 7.0],
    # 3. 박준호 — 약 완전 중단 사례 (dm_med_count 2 → 0)
    ["D3456", "박준호", "남", "1980-06-25", "초진", "2025-03-05",
     42, 36, 3, 1, 2, 0,
     7.2, 138, 1.24, 188, 165, 45, 110,
     0.92, 132, 84, 176, 82,
     32, 40, 55,
     1, 2, 1, 1, 2, 1, 0, 6.0, 1.020,
     1, 1, 1, 6.0],
    ["D3456", "박준호", "남", "1980-06-25", "졸업", "2025-06-10",
     42, 39, 3, 0, 0, 0,
     5.5, 92, 2.41, 170, 118, 55, 92,
     0.88, 118, 74, 176, 77,
     24, 26, 32,
     1, 1, 1, 1, 2, 1, 0, 6.5, 1.015,
     0, 1, 2, 7.5],
]

# ── 코딩북 ─────────────────────────────────────────────────────────────
CODEBOOK = [
    ("식별/방문", "chart_no", "차트번호", "-", "필수", "문자",
     "병원 차트번호. 같은 환자의 초진·졸업 2행이 이 값으로 묶입니다. 반드시 동일하게."),
    ("식별/방문", "name", "환자명", "-", "필수", "문자",
     "실명으로 적으셔도 됩니다. 화면에는 '김*수'처럼 자동으로 가려 표시됩니다."),
    ("식별/방문", "sex", "성별", "-", "필수", "남 / 여", "M/F, 1/2 도 인식합니다."),
    ("식별/방문", "dob", "생년월일", "-", "권장", "YYYY-MM-DD",
     "나이를 자동 계산합니다. 생년만 아는 경우 1968-01-01 처럼 적으셔도 됩니다."),
    ("식별/방문", "visit_type", "방문 구분", "-", "필수", "초진 / 졸업",
     "★가장 중요★ 이 값으로 치료 전/후를 나눕니다. 한 환자당 '초진' 1행 + '졸업' 1행."),
    ("식별/방문", "visit_date", "검사일", "-", "필수", "YYYY-MM-DD",
     "그 검사를 시행한 날짜. 초진=치료 시작일, 졸업=치료 종료일."),

    ("당뇨 이력", "dm_diagnosis_age", "당뇨 진단 나이", "세", "권장", "정수", "당뇨를 처음 진단받은 나이."),
    ("당뇨 이력", "dm_duration_months", "유병기간", "개월", "권장", "정수",
     "★년이 아니라 개월★ 7년이면 84 로 적습니다."),
    ("당뇨 이력", "treatment_months", "한약 복용기간", "개월", "권장", "정수",
     "숫자만 (6개월 → 6). 12개월을 넘으면 유사사례 후보에서 제외됩니다."),
    ("당뇨 이력", "dm_medication", "당뇨약 복용 여부", "-", "권장", "0=안함, 1=복용", "O/X 가 아니라 0/1 로."),
    ("당뇨 이력", "dm_med_count", "당뇨약 개수", "개", "권장", "정수(0 이상)",
     "★초진 행과 졸업 행에 각각 그 시점의 개수를 적어주세요★ 화면에 '2개 → 0개'처럼 "
     "감소가 표시되고, 졸업 시 0이면 '단약 성공'으로 강조됩니다. "
     "'단약'·'많이' 같은 글자는 인식되지 않으니 약을 끊었으면 숫자 0, 모르면 빈칸."),
    ("당뇨 이력", "insulin_medication", "인슐린 투여", "-", "권장", "0=안함, 1=투여", ""),

    ("혈당", "hba1c", "당화혈색소(HbA1c)", "%", "필수", "숫자", "★없으면 그 환자는 통째로 제외됩니다.★"),
    ("혈당", "fbg", "공복혈당", "mg/dL", "필수", "숫자", ""),
    ("혈당", "c_peptide", "C-peptide", "ng/mL", "필수", "숫자",
     "병원 측정값 그대로. 별도 환산 필요 없습니다. 췌장 기능 회복을 보여주는 핵심 지표."),

    ("지질", "total_cholesterol", "총콜레스테롤", "mg/dL", "필수", "숫자", ""),
    ("지질", "triglycerides", "중성지방(TG)", "mg/dL", "필수", "숫자", ""),
    ("지질", "hdl", "HDL 콜레스테롤", "mg/dL", "필수", "숫자", ""),
    ("지질", "ldl", "LDL 콜레스테롤", "mg/dL", "선택", "숫자", "실측값이 있으면 적고, 없으면 비우세요(자동 계산)."),

    ("신장", "cr", "크레아티닌(Cr)", "mg/dL", "필수", "숫자",
     "eGFR(신장기능)을 자동 계산합니다. 신장 회복 사례를 보여주는 근거가 됩니다."),

    ("혈압", "sbp", "수축기 혈압", "mmHg", "필수", "정수", ""),
    ("혈압", "dbp", "이완기 혈압", "mmHg", "필수", "정수", ""),

    ("신체", "height", "키", "cm", "필수", "숫자", "BMI 를 자동 계산합니다."),
    ("신체", "weight", "몸무게", "kg", "필수", "숫자", ""),

    ("간효소", "ast", "AST", "U/L", "선택", "숫자", ""),
    ("간효소", "alt", "ALT", "U/L", "선택", "숫자", ""),
    ("간효소", "ggt", "GGT", "U/L", "선택", "숫자", ""),

    ("소변", "he_upro", "요단백", "등급", "선택", "1~6",
     "1=음성, 2=±(경계), 3=1+, 4=2+, 5=3+, 6=4+"),
    ("소변", "he_uglu", "요당", "등급", "선택", "1~6", "위와 동일"),
    ("소변", "he_ubld", "요잠혈", "등급", "선택", "1~4", "1=음성, 2=±, 3=1+, 4=2+"),
    ("소변", "urine_bil", "요빌리루빈", "등급", "선택", "1~4", "1=음성, 2=±, 3=1+, 4=2+"),
    ("소변", "urine_uro", "우로빌리노겐", "등급", "선택", "1~4",
     "1=음성, 2=±(정상), 3=1+, 4=2+  ※ 우로빌리노겐은 ±가 정상입니다."),
    ("소변", "urine_ket", "요케톤", "등급", "선택", "1~4", "1=음성, 2=±, 3=1+, 4=2+"),
    ("소변", "urine_nit", "요아질산염", "-", "선택", "0=음성, 1=양성", ""),
    ("소변", "urine_ph", "요 산도(pH)", "pH", "선택", "숫자", "예: 6.0"),
    ("소변", "urine_sg", "요 비중(SG)", "-", "선택", "숫자", "예: 1.020"),

    ("생활습관", "smoking", "흡연", "-", "선택", "0=안함, 1=흡연", ""),
    ("생활습관", "drinking", "음주", "-", "선택", "0~3",
     "0=안함, 1=가끔, 2=자주, 3=매일"),
    ("생활습관", "exercise", "운동", "-", "선택", "0~3",
     "0=안함, 1=가끔, 2=주1~2회, 3=주3회 이상"),
    ("생활습관", "sleep_hours", "수면 시간", "시간", "선택", "숫자", "하루 평균. 예: 6.5"),
]

NOTES = [
    ("■ 이 파일은 무엇인가요?", ""),
    ("", "당뇨 프로그램을 졸업한 환자의 '치료 전(초진)'과 '치료 후(졸업)' 검사 결과를 담는 파일입니다."),
    ("", "이 데이터로 신규 환자에게 '나와 비슷했던 분이 이렇게 좋아졌다'는 유사사례를 보여줍니다."),
    ("", ""),
    ("■ 가장 중요한 구조 — 환자 1명 = 2행", ""),
    ("", "한 환자당 두 줄을 적습니다. 두 줄의 chart_no 는 반드시 같아야 합니다."),
    ("", "   · 1행: visit_type = 초진   (치료 시작 시점 검사)"),
    ("", "   · 2행: visit_type = 졸업   (치료 종료 시점 검사)"),
    ("", "두 줄 중 하나라도 없으면 그 환자는 유사사례에 사용되지 않습니다."),
    ("", ""),
    ("■ 합병증 위험도는 직접 적지 않으셔도 됩니다", ""),
    ("", "프로그램이 각 시점의 검사수치를 AI 모델에 넣어 6개 합병증(말초신경병증·망막병증·"),
    ("", "신장질환·심혈관·뇌혈관·치매) 위험도를 자동으로 계산합니다."),
    ("", "→ 검사수치만 정확히 채워주시면 '치료 전 72점 → 치료 후 38점' 같은 변화가 자동 표시됩니다."),
    ("", "→ 단, 아래 '필수' 항목이 하나라도 비면 그 시점의 합병증 위험도는 계산되지 않습니다."),
    ("", ""),
    ("■ 사용 방법", ""),
    ("", "1) '데이터' 시트에 졸업자를 한 명당 2행씩 채웁니다. (예시 3명은 지우고 쓰세요)"),
    ("", "2) 프로그램 → 설정(Settings) → '졸업자 엑셀 업로드' 버튼으로 이 파일을 올립니다."),
    ("", "3) '졸업자 N명 데이터를 불러왔습니다' 메시지가 뜨면 완료입니다."),
    ("", ""),
    ("■ 꼭 기억해 주세요", ""),
    ("", "· 업로드하면 기존 졸업자 데이터를 전부 교체합니다(추가 아님)."),
    ("", "  → 항상 '전체 명단'이 담긴 파일을 올려주세요. 새로 추가된 사람만 올리면 나머지가 사라집니다."),
    ("", "· 첫 줄의 영문 컬럼명은 절대 바꾸지 마세요. 이름으로 항목을 찾습니다."),
    ("", "· 컬럼 순서는 바꾸셔도 되고, 쓰지 않는 컬럼은 열째 삭제하셔도 됩니다."),
    ("", "· 모르는 값은 0 이 아니라 '빈칸'으로 두세요. 0 은 '실제로 0'이라는 뜻이 됩니다."),
    ("", "· 숫자 칸에는 숫자만. 단위·기호·설명(예: '6개월', '2알', '단약', 'x')은 인식되지 않습니다."),
    ("", ""),
    ("■ 자주 하는 실수", ""),
    ("", "· 약을 끊은 경우 → '단약'(X)  ...  0 (O)"),
    ("", "· 한약복용기간 → '6개월'(X)  ...  6 (O)"),
    ("", "· 유병기간 → 7 (년, X)  ...  84 (개월, O)"),
    ("", "· 모르는 값 → 0 (X)  ...  빈칸 (O)"),
    ("", "· 초진·졸업의 chart_no 가 다름 (X)  ...  동일하게 (O)"),
    ("", "· 한 환자를 1행에 전/후 나란히 적기 (X)  ...  2행으로 나누기 (O)"),
]


def _hdr(ws, ncols, fill="4F46E5", height=30):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = height


def main():
    df = pd.DataFrame(ROWS, columns=COLUMNS)
    cb = pd.DataFrame(CODEBOOK, columns=["그룹", "컬럼명(영문)", "항목명", "단위", "필수", "입력 형식", "설명 · 주의사항"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="데이터", index=False)
        cb.to_excel(xw, sheet_name="코딩북", index=False)
        pd.DataFrame(NOTES, columns=["구분", "내용"]).to_excel(xw, sheet_name="작성방법", index=False)

        wb = xw.book
        # 시트1 데이터
        ws = wb["데이터"]
        _hdr(ws, len(COLUMNS))
        for i, name in enumerate(COLUMNS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(11, min(20, len(name) + 5))
            if name in REQUIRED:
                ws.cell(row=1, column=i).fill = PatternFill("solid", fgColor="B91C1C")  # 필수=빨강
            elif name in KEY_COLS:
                ws.cell(row=1, column=i).fill = PatternFill("solid", fgColor="D97706")  # 키=주황
        for r in range(2, len(ROWS) + 2):
            for c in range(1, len(COLUMNS) + 1):
                ws.cell(row=r, column=c).alignment = Alignment(horizontal="center")
            # 초진/졸업 행 구분 음영
            if ws.cell(row=r, column=5).value == "졸업":
                for c in range(1, len(COLUMNS) + 1):
                    ws.cell(row=r, column=c).fill = PatternFill("solid", fgColor="EEF2FF")

        # 시트2 코딩북
        ws2 = wb["코딩북"]
        _hdr(ws2, 7, fill="0F766E")
        for col, w in zip("ABCDEFG", (11, 22, 20, 9, 8, 18, 62)):
            ws2.column_dimensions[col].width = w
        for r in range(2, len(CODEBOOK) + 2):
            for c in (1, 4, 5):
                ws2.cell(row=r, column=c).alignment = Alignment(horizontal="center", vertical="top")
            for c in (6, 7):
                ws2.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")
            ws2.row_dimensions[r].height = 30
            req = ws2.cell(row=r, column=5).value
            if req == "필수":
                ws2.cell(row=r, column=5).font = Font(bold=True, color="B91C1C")
            elif req == "권장":
                ws2.cell(row=r, column=5).font = Font(bold=True, color="C2410C")

        # 시트3 작성방법
        ws3 = wb["작성방법"]
        ws3.delete_rows(1)          # 헤더 행 제거 (안내문만)
        ws3.column_dimensions["A"].width = 4
        ws3.column_dimensions["B"].width = 108
        for r in range(1, len(NOTES) + 1):
            head = ws3.cell(row=r, column=1).value
            if head:
                ws3.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
                ws3.cell(row=r, column=1).font = Font(bold=True, size=11, color="0F766E")
            ws3.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
            ws3.row_dimensions[r].height = 18

    print(f"생성: {OUT.name}")
    print(f"  시트1 '데이터'    — 컬럼 {len(COLUMNS)}개, 예시 {len(ROWS)}행(환자 3명 × 초진/졸업)")
    print(f"  시트2 '코딩북'    — {len(CODEBOOK)}개 항목 코드값 정의")
    print(f"  시트3 '작성방법'  — 안내 {len(NOTES)}줄")


if __name__ == "__main__":
    main()
