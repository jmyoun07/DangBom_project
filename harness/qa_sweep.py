#!/usr/bin/env python
"""새벽 QA 자동 스윕 — 의료진 "의아함" 탐지기.

전 환자 × (대시보드 predict_all + 시나리오 simulate) 를 돌려
수치/등급/일관성/현실성 이상을 자동 검출한다. 어디서 실행하든 동작하도록
backend 경로를 직접 잡는다.

실행: <repo>/backend/.venv/bin/python harness/qa_sweep.py
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
BACKEND = "/Users/saipe/DangBom_project/backend"
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

from models.database import SessionLocal, Patient            # noqa: E402
from models.schemas import ScenarioRequest                   # noqa: E402
from ml.predictor import predict_all, get_disease_threshold  # noqa: E402
from routers.scenario import scenario_simulate               # noqa: E402

NAME_MAP = {
    "kidney_disease": "kidney", "retinopathy": "retina", "cardiovascular": "cardio",
    "neuropathy": "neuro", "dementia": "dementia", "cerebrovascular": "cerebro",
}
LOW_AUC = {"neuro", "dementia", "cerebro"}            # 신규 3개 저정확도 모델
RANK = {"저위험": 0, "중위험": 1, "고위험": 2, None: -1, "분석 진행 중": -1}
VALID_LEVELS = {"저위험", "중위험", "고위험"}

issues = []  # (severity, category, patient, detail)


def add(sev, cat, pat, detail):
    issues.append((sev, cat, pat, detail))


def metric_abnormal(short, p):
    """대시보드 카드가 보여주는 핵심 지표의 정상범위 이탈 여부 (None=판정생략)."""
    egfr = getattr(p, "egfr", None)
    sbp = getattr(p, "sbp", None)
    hdl = getattr(p, "hdl", None)
    bmi = getattr(p, "bmi", None)
    if short == "kidney":
        return egfr is not None and egfr < 60
    if short == "cardio":
        return sbp is not None and sbp >= 140
    if short == "neuro":
        return hdl is not None and hdl < 40
    if short == "cerebro":
        return bmi is not None and bmi >= 25
    return None  # retina / dementia: 지표 기반 판정 생략


def main():
    db = SessionLocal()
    patients = db.query(Patient).all()
    for p in patients:
        pdict = {c.name: getattr(p, c.name) for c in p.__table__.columns}
        pname = f"{p.name}(id{p.id},A1c{p.hba1c})"

        # ---- 대시보드 (predict_all → clinical_floor 적용) ----
        try:
            dash = predict_all(pdict)
        except Exception as e:
            add("CRIT", "dashboard_error", pname, f"predict_all 예외: {e}")
            continue

        dash_level = {}
        for full, short in NAME_MAP.items():
            info = dash.get(full, {})
            if not info.get("available"):
                dash_level[short] = None
                continue
            score = info.get("score")
            level = info.get("level")
            dash_level[short] = level
            if score is None or not (0 <= score <= 100):
                add("CRIT", "score_range", pname, f"{short} score={score}")
            if level not in VALID_LEVELS:
                add("CRIT", "level_invalid", pname, f"{short} level={level}")
                continue
            if RANK[level] >= 1:  # 중/고위험만 사유 점검
                flags = info.get("clinical_flags") or []
                reasons = info.get("clinical_floor_reasons") or []
                th = get_disease_threshold(short, age=p.age) or 30
                ml_high = score is not None and score >= th
                mab = metric_abnormal(short, p)
                has_clinical_reason = bool(flags) or bool(reasons) or (mab is True)
                if not has_clinical_reason and not ml_high:
                    add("HIGH", "F5_unexplained", pname,
                        f"{short} {level} 인데 지표정상+flag없음+score {score}<th {th} → 의아함")
                elif not has_clinical_reason and ml_high and short in LOW_AUC:
                    add("MED", "F5_lowAUC_only", pname,
                        f"{short} {level} 저AUC 모델 단독판정(지표정상, score {score}>=th {th})")
                elif has_clinical_reason and (mab is False):
                    add("LOW", "F5_reason_hidden", pname,
                        f"{short} {level} 지표정상인데 floor/flag 상향 → 카드에 사유노출 권장")

        # ---- 시나리오 (기본 슬라이더 = 현재 수치) ----
        try:
            req = ScenarioRequest(patient_id=p.id,
                                  c_peptide=(p.c_peptide or 2.0),
                                  hba1c=(p.hba1c or 7.5))
            r = scenario_simulate(req, db)["data"]
        except Exception as e:
            add("CRIT", "scenario_error", pname, f"scenario_simulate 예외: {e}")
            continue

        for k, v in r["radar"].items():
            if v is None or not (0 <= v <= 100):
                add("CRIT", "radar_range", pname, f"{k}={v}")

        neg, inten, grad = r["neglect"], r["intensive"], r["graduation"]
        for label, sc in [("neglect", neg), ("intensive", inten), ("graduation", grad)]:
            le = sc.get("life_expectancy")
            if le is None or not (40 <= le <= 110):
                add("HIGH", "life_range", pname, f"{label} life={le}")
            cost = sc.get("annual_cost_man")
            if cost is None or not (0 < cost <= 5000):
                add("HIGH", "cost_range", pname, f"{label} cost={cost}")

        if not (0 <= neg.get("insulin_probability", 0) <= 100):
            add("MED", "insulin_pct", pname, str(neg.get("insulin_probability")))
        db_b, db_a = neg.get("drug_count_before", 0), neg.get("drug_count_after", 0)
        if not (0 <= db_b <= 5 and 0 <= db_a <= 5):
            add("MED", "drug_count", pname, f"{db_b}->{db_a}")
        if db_a < db_b:
            add("MED", "drug_decrease", pname, "방치인데 약 감소(역방향)")

        ha, ca = inten.get("hba1c_after"), inten.get("cpeptide_after")
        if ha is None or not (4.5 <= ha <= 15):
            add("MED", "hba1c_after", pname, str(ha))
        if ca is None or not (0.2 <= ca <= 6):
            add("MED", "cpep_after", pname, str(ca))

        gl, il, nl = grad["life_expectancy"], inten["life_expectancy"], neg["life_expectancy"]
        gc, ic, nc = grad["annual_cost_man"], inten["annual_cost_man"], neg["annual_cost_man"]
        if not gl >= il >= nl:
            add("HIGH", "mono_life", pname, f"졸업{gl}/집중{il}/방치{nl}")
        if not gc <= ic <= nc:
            add("HIGH", "mono_cost", pname, f"졸업{gc}/집중{ic}/방치{nc}")

        # F2 일관성: 방치 등급은 대시보드 등급보다 낮으면 안 됨 (과소표시 금지)
        neg_level = {k: v["level"] for k, v in neg["complications"].items()}
        for short in NAME_MAP.values():
            d, n = dash_level.get(short), neg_level.get(short)
            if d is not None and RANK.get(n, -1) < RANK.get(d, -1):
                add("HIGH", "F2_underreport", pname, f"{short} dash={d} neg={n}")

    db.close()

    # ---- 리포트 ----
    order = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3}
    issues.sort(key=lambda x: (order[x[0]], x[1]))
    from collections import Counter
    by_sev = Counter(i[0] for i in issues)
    by_cat = Counter((i[0], i[1]) for i in issues)

    print(f"환자 {len(patients)}명 검사 완료")
    print(f"발견: CRIT={by_sev['CRIT']} HIGH={by_sev['HIGH']} MED={by_sev['MED']} LOW={by_sev['LOW']}")
    print("\n--- 카테고리별 ---")
    for (sev, cat), n in sorted(by_cat.items(), key=lambda x: (order[x[0][0]], -x[1])):
        print(f"  [{sev}] {cat}: {n}건")
    print("\n--- 상세 (CRIT/HIGH 전체 + MED/LOW 카테고리당 3건) ---")
    shown = Counter()
    for sev, cat, pat, detail in issues:
        if sev in ("CRIT", "HIGH"):
            print(f"  [{sev}] {cat} | {pat} | {detail}")
        else:
            if shown[(sev, cat)] < 3:
                print(f"  [{sev}] {cat} | {pat} | {detail}")
                shown[(sev, cat)] += 1

    gate = by_sev["CRIT"] == 0 and by_sev["HIGH"] == 0
    print(f"\n=== 백엔드 수치 GATE: {'PASS' if gate else 'FAIL'} "
          f"(CRIT/HIGH 0 필요) | MED/LOW 는 검토항목 ===")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
