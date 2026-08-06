"""졸업자 업로드 견고성 — 병원 실사용 시나리오 전수 시험.

병원은 수기로 엑셀을 채우므로 날짜 형식·단위 표기·컬럼 삭제 등이 제각각이다.
여기서 깨지면 '유사사례가 안 나온다'는 형태로만 드러나 원인 파악이 어렵다.
v2.3.5 실제 회귀: 8자리 날짜('19621102')가 숫자로 변환돼 나이 산출 실패 →
합병증 위험도 누락. 단위 붙은 숫자('8.7%')도 동일.

실행: PYTHONPATH=backend python backend/tests/test_graduate_upload_robustness.py
"""
import sys, io, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from services.graduates import parse_graduates_any

# 양식 엑셀(3명 × 초진/졸업)의 '데이터' 시트를 그대로 옮겨 둔 것.
# 외부 파일을 읽지 않으므로 데이터 파일 없이 clone 한 저장소에서도 그대로 돌아간다.
_COLS = ("chart_no", "name", "sex", "dob", "visit_type", "visit_date",
         "dm_diagnosis_age", "dm_duration_months", "treatment_months",
         "dm_medication", "dm_med_count", "insulin_medication",
         "hba1c", "fbg", "c_peptide", "total_cholesterol", "triglycerides", "hdl", "ldl", "cr",
         "sbp", "dbp", "height", "weight", "ast", "alt", "ggt",
         "he_upro", "he_uglu", "he_ubld", "urine_bil", "urine_uro", "urine_ket", "urine_nit",
         "urine_ph", "urine_sg", "smoking", "drinking", "exercise", "sleep_hours")
_ROWS = [
    ("D1234", "김영수", "남", "1968-03-15", "초진", "2025-01-10", 52,  72, 6, 1, 2, 0,
     8.7, 168, 0.87, 205, 210, 41, 122, 1.12, 142, 88, 172, 78, 38, 45, 62,
     2, 3, 1, 1, 2, 1, 0, 5.5, 1.020, 0, 1, 1, 6.5),
    ("D1234", "김영수", "남", "1968-03-15", "졸업", "2025-07-14", 52,  78, 6, 1, 1, 0,
     6.1, 104, 1.62, 178, 132, 48, 104, 0.98, 124, 76, 172, 74, 28, 30, 41,
     1, 1, 1, 1, 2, 1, 0, 6.0, 1.015, 0, 1, 2, 7.0),
    ("D2345", "이정미", "여", "1962-11-02", "초진", "2025-02-20", 58,  96, 9, 1, 3, 0,
     9.4, 192, 0.68, 224, 268, 38, 132, 1.38, 156, 94, 158, 68, 42, 51, 78,
     3, 3, 2, 1, 2, 1, 0, 5.0, 1.025, 0, 0, 0, 5.5),
    ("D2345", "이정미", "여", "1962-11-02", "졸업", "2025-11-18", 58, 105, 9, 1, 1, 0,
     6.4, 108, 1.44, 182, 140, 52, 102, 1.02, 128, 78, 158, 63, 30, 33, 44,
     1, 1, 1, 1, 2, 1, 0, 6.0, 1.018, 0, 0, 2, 7.0),
    ("D3456", "박준호", "남", "1980-06-25", "초진", "2025-03-05", 42,  36, 3, 1, 2, 0,
     7.2, 138, 1.24, 188, 165, 45, 110, 0.92, 132, 84, 176, 82, 32, 40, 55,
     1, 2, 1, 1, 2, 1, 0, 6.0, 1.020, 1, 1, 1, 6.0),
    ("D3456", "박준호", "남", "1980-06-25", "졸업", "2025-06-10", 42,  39, 3, 0, 0, 0,
     5.5,  92, 2.41, 170, 118, 55,  92, 0.88, 118, 74, 176, 77, 24, 26, 32,
     1, 1, 1, 1, 2, 1, 0, 6.5, 1.015, 0, 1, 2, 7.5),
]
base = pd.DataFrame(_ROWS, columns=list(_COLS))
# 엑셀에서 읽었을 때와 같은 datetime 으로 맞춘다 (시나리오 6 이 문자열 형식을 따로 시험한다).
for _c in ("dob", "visit_date"):
    base[_c] = pd.to_datetime(base[_c])

def to_xlsx(df, sheet="데이터", extra_sheets=False):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=sheet, index=False)
        if extra_sheets:
            pd.DataFrame({"컬럼명(영문)": ["visit_type", "hba1c"], "설명": ["a", "b"]}).to_excel(w, sheet_name="코딩북", index=False)
            pd.DataFrame({"구분": ["■ 안내"], "내용": ["x"]}).to_excel(w, sheet_name="작성방법", index=False)
    return buf.getvalue()

def to_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")

def run(label, content, expect):
    try:
        rows = parse_graduates_any(content)
        n = len(rows)
        ncomp = sum(1 for r in rows if r.get("comp_before"))
        ok = (n == expect)
        print(f"  {'✅' if ok else '❌'} {label:44} → {n:3}명 (기대 {expect}) 합병증 {ncomp}")
        return ok, rows
    except Exception as e:
        print(f"  ❌ {label:44} → 예외 {type(e).__name__}: {str(e)[:60]}")
        return False, []

print("=" * 92)
print("병원 실사용 시나리오 전수 시험")
print("=" * 92)
results = []

# 1. 원본 템플릿 그대로 (3명 × 2행) + 시트 3개
results.append(run("1. 템플릿 그대로 (시트 3개 포함)", to_xlsx(base, extra_sheets=True), 3)[0])

# 2. 대량: 200명 (400행)
big = pd.concat([base.assign(chart_no=base.chart_no + f"-{i}") for i in range(67)], ignore_index=True)
results.append(run(f"2. 대량 {len(big)//2}명 ({len(big)}행)", to_xlsx(big), len(big) // 2)[0])

# 3. 필수 항목만 (선택 컬럼 전부 삭제)
req_cols = ["chart_no", "name", "sex", "visit_type", "visit_date",
            "hba1c", "fbg", "c_peptide", "total_cholesterol", "triglycerides",
            "hdl", "cr", "sbp", "dbp", "height", "weight"]
results.append(run("3. 필수 컬럼만 남기고 나머지 삭제", to_xlsx(base[req_cols]), 3)[0])

# 4. 졸업 행 누락 (한 환자)
no_grad = base.drop(base[(base.chart_no == "D1234") & (base.visit_type == "졸업")].index)
results.append(run("4. 한 환자의 졸업 행 누락 → 그 환자만 제외", to_xlsx(no_grad), 2)[0])

# 5. 차트번호 불일치 (초진/졸업 다름)
mismatch = base.copy()
mismatch.loc[(mismatch.chart_no == "D1234") & (mismatch.visit_type == "졸업"), "chart_no"] = "D1234 "
results.append(run("5. 초진/졸업 차트번호 공백 차이", to_xlsx(mismatch), 3)[0])

# 6. 날짜 형식 다양
dates = base.copy()
dates["visit_date"] = ["2025.01.10", "2025/07/14", "20250220", "2025-11-18", "2025-03-05", "2025-06-10"]
dates["dob"] = ["1968.03.15", "1968/03/15", "19621102", "1962-11-02", "1980-06-25", "1980-06-25"]
results.append(run("6. 날짜 형식 혼용 (. / 없음)", to_xlsx(dates), 3)[0])

# 7. 숫자에 단위·기호
units = base.copy()
units["hba1c"] = ["8.7%", "6.1%", "9.4", "6.4", "7.2", "5.5"]
units["treatment_months"] = ["6개월", "6개월", "9개월", "9개월", "3", "3"]
ok, rows = run("7. 숫자에 단위 포함 ('8.7%', '6개월')", to_xlsx(units), 3)
results.append(ok)
if rows:
    print(f"       → HbA1c 파싱: {[r['hba1c_before'] for r in rows]}")

# 8. visit_type 대체 라벨
alt = base.copy()
alt["visit_type"] = alt["visit_type"].replace({"초진": "치료전", "졸업": "치료후"})
results.append(run("8. visit_type '치료전/치료후' 사용", to_xlsx(alt), 3)[0])

# 9. 빈 행 섞임
blank = pd.concat([base, pd.DataFrame([{c: None for c in base.columns}] * 3)], ignore_index=True)
results.append(run("9. 아래에 빈 행 3개", to_xlsx(blank), 3)[0])

# 10. CSV 로 저장
results.append(run("10. CSV(UTF-8 BOM)로 저장", to_csv(base), 3)[0])

# 11. 시트 이름 변경
results.append(run("11. 시트 이름을 '졸업자'로 변경", to_xlsx(base, sheet="졸업자"), 3)[0])

# 12. 필수값 일부 결측 (합병증 산출 불가하지만 사례는 유지)
partial = base.copy()
partial.loc[partial.visit_type == "초진", "c_peptide"] = None
ok, rows = run("12. 초진 C-peptide 결측", to_xlsx(partial), 3)
results.append(ok)
if rows:
    print(f"       → 초진 합병증 산출: {sum(1 for r in rows if r.get('comp_before'))}/3 (결측이면 0이 정상)")

# 13. 컬럼 순서 뒤섞기
shuffled = base[list(reversed(base.columns))]
results.append(run("13. 컬럼 순서 역순", to_xlsx(shuffled), 3)[0])

# 14. 같은 환자 중복 (초진 2행)
dup = pd.concat([base, base[base.chart_no == "D1234"]], ignore_index=True)
results.append(run("14. 같은 환자 행 중복", to_xlsx(dup), 3)[0])

print("=" * 92)
print(f"결과: {sum(results)}/{len(results)} 통과")
print("=" * 92)


import unittest


class GraduateUploadRobustnessTest(unittest.TestCase):
    def test_all_scenarios_pass(self):
        self.assertEqual(sum(results), len(results),
                         "병원 실사용 시나리오 중 실패가 있습니다 — 위 출력의 ❌ 항목 확인")


if __name__ == "__main__":
    unittest.main(verbosity=0, exit=False)
