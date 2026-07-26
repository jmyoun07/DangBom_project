"""병원 실전 업무 흐름 QA — 실행 중인 dev 서버에 실제 HTTP 요청을 보내 점검한다.

사용법:
  1) 빈 DB 로 백엔드 기동 (신규 설치 재현):
       DBCARE_DB_PATH=/tmp/qa.db backend/.venv/bin/python -m uvicorn main:app --port 8000
       (backend 디렉토리에서 실행)
  2) python scripts/qa_smoke.py

배포 전 최종 관문 — 47개 항목이 모두 통과해야 빌드한다.

신규 설치(빈 DB) 상태에서 병원이 실제로 하는 순서 그대로 재현한다:
  1) 프로그램 첫 실행 (환자 0명 상태)
  2) 졸업자 데이터 업로드 (설정 탭)
  3) 환자 CSV 일괄 업로드 (병렬식 실파일)
  4) 환자 한 명 수기 등록
  5) 환자 수정
  6) 각 화면 조회 (대시보드/상세/시나리오/유사사례/검사이력/통합리포트)
  7) 재방문 데이터 추가 (같은 환자 2차 검사)
  8) 검색·필터·페이지네이션
  9) 백업·내보내기
 10) 환자 삭제
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
ROOT = "/Users/saipe/DangBom_project"

results = []
fails = []


def call(method, path, body=None, files=None, expect=200, label=None):
    url = BASE + path
    lbl = label or f"{method} {path}"
    try:
        if files:
            boundary = "----QABOUNDARY"
            fname, content = files
            payload = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(url, data=payload, method=method)
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        else:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, method=method)
            if data:
                req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=180) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:
        results.append((lbl, "EXC", False))
        fails.append(f"{lbl}: {type(e).__name__}: {e}")
        print(f"  ❌ {lbl:52} 예외 {type(e).__name__}: {str(e)[:50]}")
        return None

    ok = status == expect
    results.append((lbl, status, ok))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {lbl:52} {status}")
    if not ok:
        detail = raw[:200].decode(errors="replace")
        fails.append(f"{lbl}: {status} {detail}")
        print(f"       {detail}")
    try:
        return json.loads(raw)
    except Exception:
        return raw


print("=" * 78)
print("병원 실전 업무 흐름 QA — v2.3.5 (신규 설치 상태)")
print("=" * 78)

print("\n[1] 프로그램 첫 실행 — 빈 상태")
call("GET", "/health")
d = call("GET", "/api/v1/patients/count")
print(f"       환자 수: {d['data']['count']}명 (0 기대)")
d = call("GET", "/api/v1/graduates/count")
print(f"       졸업자: {d['data']['count']}명")
call("GET", "/api/v1/patients?page=1&size=8", label="환자 목록(빈 상태)")
call("GET", "/api/v1/diagnostics", label="진단 정보")
call("GET", "/api/v1/upload/template", label="CSV 템플릿 다운로드")

print("\n[2] 졸업자 데이터 업로드 (설정 탭)")
for f, lbl in [("졸업자_RAW_데이터셋_양식_병원발송용.xlsx", "신규 양식(롱포맷)"),
               ("졸업자_raw_데이터셋_예시.xlsx", "롱포맷 208명"),
               ("전지점 졸업자 208명 통계_260522 취합.xlsx", "기존 wide 실데이터")]:
    d = call("POST", "/api/v1/graduates/upload",
             files=(f, open(f"{ROOT}/{f}", "rb").read()), label=f"졸업자 업로드: {lbl}")
    if d and isinstance(d, dict) and d.get("data"):
        print(f"       → {d['data']['loaded']}명 적재")
# 최종적으로 롱포맷(합병증 산출됨)으로 되돌림
call("POST", "/api/v1/graduates/upload",
     files=("g.xlsx", open(f"{ROOT}/졸업자_raw_데이터셋_예시.xlsx", "rb").read()),
     label="졸업자 최종(롱포맷)")

print("\n[3] 환자 CSV 일괄 업로드 (병렬식 실파일 673행)")
d = call("POST", "/api/v1/upload/csv",
         files=("당봄.xlsx", open(f"{ROOT}/당봄_검사결과_병렬식_260723.xlsx", "rb").read()),
         label="병렬식 673행 업로드")
if d and d.get("data"):
    dd = d["data"]
    print(f"       → 신규 {dd.get('created_count')}명 / 방문 {dd.get('visits_added')} / 건너뜀 {dd.get('skipped_count')}")
    print(f"       → 경고 {len(dd.get('validation', {}).get('warnings', []))}건, 오류 {len(dd.get('validation', {}).get('errors', []))}건")

print("\n[4] 환자 한 명 수기 등록")
NEW = {"name": "QA테스트", "chart_no": "QA-0001", "dob": "1968-03-10", "sex": "F",
       "phone": "010-1111-2222", "exam_date": "2026-07-20",
       "height": 157.2, "weight": 43.4, "sbp": 96, "dbp": 67,
       "hba1c": 8.2, "fbg": 145, "c_peptide": 1.08,
       "total_cholesterol": 203, "triglycerides": 191, "hdl": 42, "ldl": 122,
       "cr": 0.64, "ast": 34, "alt": 47, "ggt": 10, "dm_med_count": 2}
d = call("POST", "/api/v1/patients", NEW, label="수기 등록(전체 필드)")
pid = d["data"]["id"] if d and d.get("data") else None
print(f"       → 환자 id={pid}")

d = call("POST", "/api/v1/patients",
         {"name": "QA최소", "chart_no": "QA-0002", "sex": "M", "dob": "1975-05-05"},
         label="수기 등록(최소 필드)")
min_id = d["data"]["id"] if d and d.get("data") else None

print("\n[5] 환자 수정")
for lbl, ch in [("검사수치만", {"hba1c": 7.1}),
                ("약 개수만", {"dm_med_count": 1}),
                ("동시 변경", {"cr": 0.9, "dm_med_count": 0, "alt": 52}),
                ("검사일 변경", {"exam_date": "2026-07-22"}),
                ("성별 변경", {"sex": "M"})]:
    call("PATCH", f"/api/v1/patients/{pid}", ch, label=f"수정: {lbl}")

print("\n[6] 각 화면 조회")
call("GET", f"/api/v1/patients/{pid}", label="환자 상세")
call("POST", "/api/v1/predict", {"patient_id": pid}, label="합병증 예측(대시보드)")
call("POST", "/api/v1/scenario/simulate",
     {"patient_id": pid, "c_peptide": 1.5, "hba1c": 7.0}, label="시나리오 분석")
call("POST", "/api/v1/predict/simulate",
     {"patient_id": pid, "c_peptide": 1.5, "hba1c": 7.0}, label="슬라이더 시뮬레이션")
d = call("GET", f"/api/v1/case-comparison/{pid}", label="유사사례")
if d and d.get("data"):
    cases = d["data"].get("cases", [])
    print(f"       → 사례 {len(cases)}건 / 졸업자 풀 {d['data'].get('graduate_count')}명")
    for c in cases:
        print(f"         · {c.get('name')} 약 {c.get('dm_med_count')}→{c.get('dm_med_count_after')} "
              f"| 합병증 {'O' if c.get('comp_before') else 'X'}")
call("GET", f"/api/v1/patients/{pid}/visits", label="검사 이력")
call("GET", f"/api/v1/patients/{pid}/integrated-report", label="통합 리포트")
call("GET", f"/api/v1/patients/{pid}/audit", label="수정 이력")
call("GET", "/api/v1/patients/by-chart/QA-0001", label="차트번호 조회")

print("\n[7] 재방문 (같은 환자 2차 검사)")
# 재방문은 같은 차트번호로 POST (PATCH 는 기존 방문 '수정')
call("POST", "/api/v1/patients",
     {**NEW, "exam_date": "2026-07-25", "hba1c": 6.4, "fbg": 108, "c_peptide": 1.9,
      "cr": 0.7, "alt": 30, "ast": 28, "ggt": 12, "dm_med_count": 0},
     label="2차 검사 입력(재방문 POST)")
d = call("GET", f"/api/v1/patients/{pid}/visits", label="방문 2건 확인")
if d and d.get("data"):
    v = d["data"] if isinstance(d["data"], list) else d["data"].get("visits", [])
    print(f"       → 방문 {len(v)}건")
d = call("GET", f"/api/v1/patients/{pid}/integrated-report", label="통합리포트(2회차)")
if d and d.get("data"):
    vs = d["data"].get("visits", [])
    for x in vs:
        m = x.get("measured", {})
        print(f"         · {x.get('measured_at')}: HbA1c {m.get('hba1c')} ALT {m.get('alt')} AST {m.get('ast')} GGT {m.get('ggt')}")

print("\n[8] 검색·필터·페이지네이션")
call("GET", "/api/v1/patients?search=QA", label="이름 검색")
call("GET", "/api/v1/patients?search=QA-0001", label="차트번호 검색")
call("GET", "/api/v1/patients?search=010-1111", label="연락처 검색")
call("GET", "/api/v1/patients?risk_level=%EA%B3%A0%EC%9C%84%ED%97%98", label="위험도 필터")
call("GET", "/api/v1/patients?page=2&size=8", label="2페이지")
call("GET", "/api/v1/patients?page=999&size=8", label="범위 밖 페이지")

print("\n[9] 백업·내보내기")
call("GET", "/api/v1/patients/backup", label="전체 백업 CSV")
call("GET", "/api/v1/export/folder", label="내보내기 폴더")
call("POST", "/api/v1/export/refresh", label="내보내기 갱신")

print("\n[10] 삭제")
call("DELETE", f"/api/v1/patients/{min_id}", label="환자 삭제(최소)")
call("GET", f"/api/v1/patients/{min_id}", expect=404, label="삭제 확인(404 기대)")

print("\n[11] 잘못된 입력 방어 (4xx 기대)")
call("GET", "/api/v1/patients/9999999", expect=404, label="없는 환자")
call("POST", "/api/v1/patients", {"name": "X"}, expect=422, label="필수 누락")
call("POST", "/api/v1/patients", {"name": "미래", "chart_no": "QA-F", "sex": "M",
     "dob": "2099-01-01"}, expect=422, label="미래 생년월일")
call("POST", "/api/v1/predict", {"patient_id": 9999999}, expect=404, label="없는 환자 예측")
call("POST", "/api/v1/graduates/upload", files=("bad.txt", b"not an excel"),
     expect=400, label="잘못된 파일 업로드")
call("GET", "/api/v1/nonexistent", expect=404, label="없는 API 경로")

print("\n" + "=" * 78)
ok = sum(1 for _, _, o in results if o)
print(f"결과: {ok}/{len(results)} 통과")
if fails:
    print(f"\n실패 {len(fails)}건:")
    for f in fails:
        print(f"  ✗ {f}")
    sys.exit(1)
print("전 항목 통과 ✅")
