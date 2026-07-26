"""병원 배포용 졸업자 데이터 입력 템플릿 생성.

시트 2개:
  1) '졸업자 리스트'  — 파서가 실제로 읽는 컬럼 + 예시 8행 (병원은 이 시트를 채운다)
  2) '작성방법'       — 컬럼별 코딩 규칙·유의사항

컬럼명은 backend/services/graduates.py 의 col(...) 별칭과 정확히 일치해야 한다.
실행: python scripts/make_graduate_template.py
"""
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent.parent / "졸업자_입력템플릿_병원발송용.xlsx"

# ── 시트1: 파서가 읽는 컬럼 (순서 = 입력 편의 순) ──────────────────────
COLUMNS = [
    # 식별
    "챠트번호", "환자명", "성별", "결제일 기준 나이",
    # 치료 개요
    "한약복용기간", "유병기간(개월차)", "초진BMI", "당뇨약 개수", "목표",
    # 핵심 지표 (필수)
    "치료전", "치료후", "감소 차이",
    # 보강 지표 (있으면 유사사례 품질 ↑)
    "C펩타이드_치료전", "C펩타이드_치료후",
    "eGFR_치료전", "eGFR_치료후",
    # 합병증 전/후 (0~100 위험도 또는 0/1 유무)
    "말초신경병증_치료전", "말초신경병증_치료후",
    "망막병증_치료전", "망막병증_치료후",
    "신장질환_치료전", "신장질환_치료후",
    "심혈관질환_치료전", "심혈관질환_치료후",
    "뇌혈관질환_치료전", "뇌혈관질환_치료후",
    "치매_치료전", "치매_치료후",
    # 증상
    "당뇨발저림", "호전 정도",
]

EXAMPLE_ROWS = [
    # 완전 입력 예시 — 모든 항목이 채워진 이상적인 행
    ["D1234", "김영수", "남", 58, 6, 84, 26.4, 2, "당뇨완치",
     8.7, 6.1, 2.6, 0.9, 1.6, 52, 68,
     72, 38, 61, 22, 70, 31, 74, 45, 73, 42, 58, 30,
     "당뇨발저림", "소실"],
    # 신장 회복 사례 — eGFR 60 미만 → 회복 (유사사례 '신장 회복' 카드에 쓰임)
    ["D2345", "이정미", "여", 63, 9, 120, 24.1, 3, "당뇨초기",
     9.4, 6.4, 3.0, 0.7, 1.4, 48, 66,
     78, 44, 66, 30, 82, 40, 77, 48, 76, 46, 62, 35,
     "종아리 쥐", "호전"],
    # 당뇨약 완전 중단 사례 — '단약' 이 아니라 숫자 0 으로 적는다
    ["D3456", "박준호", "남", 45, 3, 36, 22.8, 0, "당뇨졸업",
     7.2, 5.5, 1.7, 1.8, 2.4, 88, 95,
     34, 12, 28, 8, 30, 10, 36, 15, 33, 13, 20, 8,
     None, None],
    # 보강 지표 일부만 있는 경우 — 빈칸으로 두면 됨(0 으로 적지 말 것)
    ["D4567", "최은희", "여", 52, 4, 60, 27.9, 1, "혈당안정화",
     7.8, 6.0, 1.8, 1.1, 1.7, None, None,
     None, None, None, None, None, None, None, None, None, None, None, None,
     "발 냉증", "약간 호전"],
    # 핵심 지표만 있는 최소 입력 — 이 정도만 채워도 유사사례에 사용됨
    ["D5678", "정해강", "남", 67, 6, 156, 23.5, 2, "당뇨초기",
     10.2, 7.1, 3.1, None, None, None, None,
     None, None, None, None, None, None, None, None, None, None, None, None,
     None, None],
    # 인슐린 → 경구약 전환 등 개선폭이 큰 사례
    ["D6789", "한소라", "여", 49, 12, 204, 29.3, 4, "당뇨완치",
     11.8, 6.3, 5.5, 0.5, 1.2, 44, 59,
     85, 46, 74, 33, 88, 42, 83, 50, 84, 49, 70, 38],
    # 나이·유병기간이 짧은 초기 환자
    ["D7890", "오민석", "남", 38, 3, 12, 25.0, 1, "당뇨초기",
     6.9, 5.6, 1.3, 1.5, 2.1, 95, 102,
     26, 10, 20, 6, 22, 8, 28, 12, 25, 10, 15, 6,
     None, None],
    # 치료 후에도 목표 미달이나 개선된 사례 (악화 아님)
    ["D8901", "윤지아", "여", 71, 9, 240, 21.7, 3, "혈당안정화",
     9.9, 7.4, 2.5, 0.6, 1.0, 51, 58,
     80, 55, 71, 44, 79, 52, 82, 58, 81, 56, 74, 50,
     "당뇨발저림", "비슷함"],
]

# ── 시트2: 작성 방법 ────────────────────────────────────────────────
GUIDE_HEADER = ["구분", "컬럼명", "필수", "입력 형식", "작성 요령 · 주의사항"]
GUIDE_ROWS = [
    ("식별", "챠트번호", "필수", "문자 (예: D1234)",
     "병원 차트번호 그대로. 같은 환자가 여러 번 졸업했다면 각각 다른 행으로 넣습니다."),
    ("식별", "환자명", "필수", "문자 (예: 김영수)",
     "실명으로 적으셔도 됩니다. 화면에는 자동으로 '김*수'처럼 가려서 표시됩니다."),
    ("식별", "성별", "필수", "남 / 여",
     "'남'/'여' 로 적습니다. M/F, 1/2 도 인식합니다. 뒤에 공백이 있어도 괜찮습니다."),
    ("식별", "결제일 기준 나이", "권장", "숫자 (예: 58)",
     "치료 시작 시점의 만 나이. 유사사례를 나이대로 매칭하므로 가급적 채워주세요."),

    ("치료 개요", "한약복용기간", "필수", "숫자, 개월 (예: 6)",
     "'6개월' 이 아니라 숫자 6 만 적습니다. 12개월을 넘는 사례는 유사사례 후보에서 제외됩니다."),
    ("치료 개요", "유병기간(개월차)", "권장", "숫자, 개월 (예: 84)",
     "당뇨 진단 후 경과 개월수. 7년이면 84 로 적습니다(년 아님). 유사사례 매칭에 사용됩니다."),
    ("치료 개요", "초진BMI", "권장", "숫자 (예: 26.4)",
     "치료 시작 시 BMI. 소수점 한 자리까지."),
    ("치료 개요", "당뇨약 개수", "권장", "숫자만 (예: 0, 1, 2)",
     "★가장 많이 잘못 적히는 항목★ '단약'·'많이'·'약간'·'x' 같은 글자는 인식되지 않고 버려집니다. "
     "약을 끊었으면 반드시 숫자 0, 모르면 빈칸으로 두세요."),
    ("치료 개요", "목표", "선택", "문자 (예: 당뇨완치)",
     "치료 목표만 적습니다. '카트1'·'카트2 윗칸'·'NEW' 같은 서류 보관 위치는 적지 마세요(다른 칸으로 분리)."),

    ("핵심 지표", "치료전", "필수", "숫자, % (예: 8.7)",
     "치료 시작 시 당화혈색소(HbA1c). ★이 값이 비면 그 행은 통째로 제외됩니다.★"),
    ("핵심 지표", "치료후", "필수", "숫자, % (예: 6.1)",
     "치료 종료 시 당화혈색소. ★이 값이 비면 그 행은 통째로 제외됩니다.★"),
    ("핵심 지표", "감소 차이", "자동", "숫자 (예: 2.6)",
     "치료전 − 치료후. 비워두면 자동 계산되므로 그냥 두셔도 됩니다."),

    ("보강 지표", "C펩타이드_치료전 / _치료후", "권장", "숫자, ng/mL (예: 0.9 / 1.6)",
     "췌장 기능 회복을 보여주는 핵심 지표입니다. 채우시면 '췌장 기능이 이만큼 좋아졌다'는 "
     "사례를 환자에게 제시할 수 있습니다."),
    ("보강 지표", "eGFR_치료전 / _치료후", "권장", "숫자 (예: 52 / 68)",
     "신장 기능(사구체여과율). 치료전이 60 미만이었다가 오른 사례는 '신장 기능 회복' 사례로 "
     "따로 뽑혀 표시됩니다. 지금은 이 값이 없어 해당 사례가 나오지 않습니다."),

    ("합병증", "○○○_치료전 / _치료후", "선택", "0~100 위험도 (예: 72 / 38)",
     "6개 합병증(말초신경병증·망막병증·신장질환·심혈관질환·뇌혈관질환·치매)의 치료 전후 위험도. "
     "0~100 숫자로 적으면 사례 카드에 '전 → 후' 막대가 표시됩니다. 모르면 전부 비워두세요."),

    ("증상", "당뇨발저림 / 호전 정도", "선택", "문자",
     "증상명과 호전 정도(소실/호전/약간 호전/비슷함)를 적습니다. 참고용이며 매칭에는 쓰지 않습니다."),
]

NOTES = [
    ("■ 이 파일을 어떻게 쓰나요?", ""),
    ("", "1) '졸업자 리스트' 시트에 졸업자를 한 명당 한 행씩 채웁니다."),
    ("", "2) 프로그램 → 설정(Settings) → '졸업자 엑셀 업로드' 버튼을 눌러 이 파일을 올립니다."),
    ("", "3) '졸업자 N명 데이터를 불러왔습니다' 메시지가 뜨면 완료입니다."),
    ("", ""),
    ("■ 꼭 기억해 주세요", ""),
    ("", "· 업로드하면 기존 졸업자 데이터를 전부 교체합니다(추가 아님)."),
    ("", "  → 항상 '전체 명단'이 담긴 파일을 올려주세요. 새로 추가된 사람만 올리면 나머지가 사라집니다."),
    ("", "· 시트 이름 '졸업자 리스트' 와 첫 줄의 컬럼명은 바꾸지 마세요. 이름으로 항목을 찾습니다."),
    ("", "· 컬럼 순서는 바꾸셔도 되고, 쓰지 않는 컬럼은 열째 삭제하셔도 됩니다."),
    ("", "· 모르는 값은 0 이 아니라 '빈칸'으로 두세요. 0 은 '실제로 0'이라는 뜻이 됩니다."),
    ("", "· 숫자 칸에는 숫자만 적어주세요. 단위·기호·설명(예: '6개월', '2알', '단약')은 인식되지 않습니다."),
    ("", ""),
    ("■ 자주 나오는 실수", ""),
    ("", "· 당뇨약을 끊은 경우 → '단약'(X)  ...  0 (O)"),
    ("", "· 한약복용기간 → '6개월'(X)  ...  6 (O)"),
    ("", "· 유병기간 → 7년(X)  ...  84 (개월, O)"),
    ("", "· 모르는 값 → 0 (X)  ...  빈칸 (O)"),
    ("", "· '목표' 칸에 서류 보관 위치('카트1' 등) 적기 (X)"),
    ("", ""),
    ("■ 최소 입력 기준", ""),
    ("", "챠트번호 · 환자명 · 성별 · 한약복용기간 · 치료전 · 치료후 만 있어도 유사사례에 사용됩니다."),
    ("", "나머지를 채우실수록 환자에게 더 구체적인 사례(췌장 기능 회복, 신장 회복 등)를 보여줄 수 있습니다."),
]


def _style_header(ws, ncols, fill="4F46E5"):
    thin = Side(style="thin", color="D1D5DB")
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=thin)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30


def main():
    df_data = pd.DataFrame(EXAMPLE_ROWS, columns=COLUMNS)
    df_guide = pd.DataFrame(GUIDE_ROWS, columns=GUIDE_HEADER)

    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        df_data.to_excel(xw, sheet_name="졸업자 리스트", index=False)
        df_guide.to_excel(xw, sheet_name="작성방법", index=False, startrow=0)

        wb = xw.book
        ws1 = wb["졸업자 리스트"]
        ws2 = wb["작성방법"]

        # ── 시트1 스타일 ──
        _style_header(ws1, len(COLUMNS))
        widths = {"챠트번호": 11, "환자명": 10, "성별": 7, "결제일 기준 나이": 15,
                  "한약복용기간": 13, "유병기간(개월차)": 15, "초진BMI": 10,
                  "당뇨약 개수": 12, "목표": 13, "치료전": 9, "치료후": 9, "감소 차이": 10,
                  "당뇨발저림": 13, "호전 정도": 11}
        for i, name in enumerate(COLUMNS, start=1):
            ws1.column_dimensions[get_column_letter(i)].width = widths.get(name, 17)
        # 필수 컬럼 헤더 강조(주황)
        for name in ("챠트번호", "환자명", "성별", "한약복용기간", "치료전", "치료후"):
            ws1.cell(row=1, column=COLUMNS.index(name) + 1).fill = PatternFill("solid", fgColor="D97706")
        for r in range(2, len(EXAMPLE_ROWS) + 2):
            for c in range(1, len(COLUMNS) + 1):
                ws1.cell(row=r, column=c).alignment = Alignment(horizontal="center")

        # ── 시트2 스타일 ──
        _style_header(ws2, len(GUIDE_HEADER), fill="0F766E")
        for col, w in zip("ABCDE", (11, 26, 8, 24, 88)):
            ws2.column_dimensions[col].width = w
        for r in range(2, len(GUIDE_ROWS) + 2):
            ws2.cell(row=r, column=5).alignment = Alignment(wrap_text=True, vertical="top")
            ws2.cell(row=r, column=1).alignment = Alignment(horizontal="center", vertical="top")
            ws2.cell(row=r, column=3).alignment = Alignment(horizontal="center", vertical="top")
            ws2.row_dimensions[r].height = 34
            req = ws2.cell(row=r, column=3).value
            if req == "필수":
                ws2.cell(row=r, column=3).font = Font(bold=True, color="B91C1C")
            elif req == "권장":
                ws2.cell(row=r, column=3).font = Font(bold=True, color="C2410C")

        # 안내문 블록 추가
        start = len(GUIDE_ROWS) + 3
        for i, (head, body) in enumerate(NOTES):
            r = start + i
            if head:
                cell = ws2.cell(row=r, column=1, value=head)
                cell.font = Font(bold=True, size=11, color="0F766E")
                ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
            elif body:
                cell = ws2.cell(row=r, column=2, value=body)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                ws2.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
            ws2.row_dimensions[r].height = 20

    print(f"생성 완료: {OUT}")
    print(f"  시트1 '졸업자 리스트' — 컬럼 {len(COLUMNS)}개, 예시 {len(EXAMPLE_ROWS)}행")
    print(f"  시트2 '작성방법' — 가이드 {len(GUIDE_ROWS)}행 + 안내 {len(NOTES)}줄")


if __name__ == "__main__":
    main()
