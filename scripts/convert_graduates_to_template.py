"""실제 졸업자 통계(전지점 208명) → 프로그램 업로드용 템플릿 양식으로 변환.

병원이 바로 Settings 에 올려 쓸 수 있는 파일을 만든다.
원본의 지저분한 값을 프로그램이 읽을 수 있게 정제하되, **추론이 불가능한 값은 비워 둔다**
(0 으로 채우면 '실제 0' 과 구분이 안 되므로).

정제 규칙 (원본 교차검증 기반):
  · 당뇨약 개수 'x' + 당뇨약 여부 'X'  → 0   (약을 복용하지 않음)
  · 당뇨약 개수 결측 + 당뇨약 여부 'X'  → 0   (동일)
  · 당뇨약 개수 '단약'/'전부 단약'      → 0   (복용하다 중단)
  · 당뇨약 개수 '많이'/'약간'          → 빈칸 (숫자 불명 — 병원이 채워야 함)
  · 목표: '카트1'·'카트2 윗칸'·'NEW' 등 서류 보관위치 → 빈칸 (치료목표만 남김)
  · 성별 앞뒤 공백 제거, 숫자 컬럼의 문자열 숫자 → 숫자

실행: python scripts/convert_graduates_to_template.py
"""
import math
import re
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "전지점 졸업자 208명 통계_260522 취합.xlsx"
OUT = ROOT / "졸업자_데이터_업로드용_최신.xlsx"

# 서류 보관 위치 (치료목표가 아님) — 목표 칸에서 제거
STORAGE_TOKENS = {"카트1", "카트2", "카트3", "카트2 윗칸", "카트2윗칸", "NEW", "new"}

# 템플릿과 동일한 컬럼 순서 (프로그램 파서가 이름으로 인식)
COLUMNS = [
    "챠트번호", "환자명", "성별", "결제일 기준 나이",
    "한약복용기간", "유병기간(개월차)", "초진BMI", "당뇨약 개수", "목표",
    "치료전", "치료후", "감소 차이",
    "C펩타이드_치료전", "C펩타이드_치료후",
    "eGFR_치료전", "eGFR_치료후",
    "말초신경병증_치료전", "말초신경병증_치료후",
    "망막병증_치료전", "망막병증_치료후",
    "신장질환_치료전", "신장질환_치료후",
    "심혈관질환_치료전", "심혈관질환_치료후",
    "뇌혈관질환_치료전", "뇌혈관질환_치료후",
    "치매_치료전", "치매_치료후",
    "당뇨발저림", "호전 정도",
]

BLANK_AFTER = COLUMNS.index("C펩타이드_치료전")   # 이후 컬럼은 원본에 없어 비움(합병증 전까지)


def num(v):
    """숫자 추출 — 문자열 '6.5' 도 처리. 불가능하면 None."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def text(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def clean_med_count(raw_count, raw_yn):
    """당뇨약 개수 정제. (값, 사유) 반환 — 사유는 변환 리포트용."""
    c = (str(raw_count).strip() if raw_count is not None else "")
    if c.lower() in ("nan", "none", ""):
        c = ""
    yn = (str(raw_yn).strip().upper() if raw_yn is not None else "")

    # 이미 숫자면 그대로
    n = num(c) if c else None
    if n is not None:
        return n, None

    if c in ("단약", "전부 단약", "전부단약"):
        return 0.0, "'단약' → 0"
    if yn == "X":                      # 약을 복용하지 않음 → 개수 0
        return 0.0, ("'x' → 0 (당뇨약 여부 X)" if c else "결측 → 0 (당뇨약 여부 X)")
    if c in ("많이", "약간"):
        return None, f"'{c}' → 빈칸 (숫자 불명, 병원 확인 필요)"
    return None, None


def main():
    df = pd.read_excel(SRC, sheet_name="졸업자 리스트", dtype=object)

    rows, report = [], {}
    dropped = 0
    for _, r in df.iterrows():
        before, after = num(r.get("치료전")), num(r.get("치료후"))
        if before is None or after is None:      # 파서와 동일 기준 — 핵심 지표 없으면 제외
            dropped += 1
            continue

        med, why = clean_med_count(r.get("당뇨약 개수"), r.get("당뇨약 여부"))
        if why:
            report[why] = report.get(why, 0) + 1

        goal = text(r.get("목표"))
        if goal in STORAGE_TOKENS:
            goal = None
            report["목표: 보관위치 → 빈칸"] = report.get("목표: 보관위치 → 빈칸", 0) + 1

        drop = num(r.get("감소 차이"))
        if drop is None:
            drop = round(before - after, 2)

        row = {c: None for c in COLUMNS}
        row.update({
            "챠트번호": text(r.get("챠트번호")),
            "환자명": text(r.get("환자명")),
            "성별": text(r.get("성별")),
            "결제일 기준 나이": num(r.get("결제일 기준 나이")),
            "한약복용기간": num(r.get("한약복용기간")),
            "유병기간(개월차)": num(r.get("유병기간(개월차)")),
            "초진BMI": num(r.get("초진BMI")),
            "당뇨약 개수": med,
            "목표": goal,
            "치료전": before,
            "치료후": after,
            "감소 차이": drop,
            "당뇨발저림": text(r.get("당뇨발저림")),
            "호전 정도": text(r.get("호전 정도")),
        })
        rows.append(row)

    out_df = pd.DataFrame(rows, columns=COLUMNS)

    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        out_df.to_excel(xw, sheet_name="졸업자 리스트", index=False)
        ws = xw.book["졸업자 리스트"]
        for i, name in enumerate(COLUMNS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(10, min(18, len(name) + 4))
            cell = ws.cell(row=1, column=i)
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            required = name in ("챠트번호", "환자명", "성별", "한약복용기간", "치료전", "치료후")
            cell.fill = PatternFill("solid", fgColor="D97706" if required else "4F46E5")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 30

    filled = out_df["당뇨약 개수"].notna().sum()
    print(f"생성: {OUT.name}")
    print(f"  {len(out_df)}명 (원본 {len(df)}행, 핵심지표 없어 제외 {dropped}행)")
    print(f"  당뇨약 개수 채워짐: {filled}/{len(out_df)}명  (변환 전 89명)")
    print("\n  정제 내역:")
    for k, v in sorted(report.items(), key=lambda x: -x[1]):
        print(f"    {v:3}건  {k}")
    print("\n  ※ C-peptide·eGFR·합병증 전후 컬럼은 원본에 없어 비어 있습니다(병원이 채우면 자동 인식).")


if __name__ == "__main__":
    main()
