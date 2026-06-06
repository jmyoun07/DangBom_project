"""
KNHANES 동일 연령대 백분위 산출.

build_percentiles.py 가 생성한 knhanes_percentiles.json 을 로드하여
환자 ML 점수가 동일 연령대 코호트 안에서 몇 percentile 에 있는지 계산.

사용:
    from services.percentile import compute_percentile, enrich_predictions
    pr = compute_percentile("kidney_disease", age=65, score=42.5)
    # → {"percentile": 73, "top_percent": 27, "bucket": "60-69", "n": 1299}
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

JSON_PATH = Path(__file__).resolve().parent.parent / "ml" / "models" / "knhanes_percentiles.json"

_CACHE: Optional[dict] = None


def _load() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
    except Exception as e:
        logger.warning(f"knhanes_percentiles.json 로드 실패: {e}")
        _CACHE = {}
    return _CACHE


def _finite(x) -> bool:
    """x 가 유한한 수치인지. None/NaN/inf/비숫자 → False.

    v2.2.6 (감사 NO-GO 수정): age/score=NaN 이 비교를 모두 false 로 만들어 '80+' 버킷이
    조용히 붙거나 fold=NaN 이 반환되던 문제 방지. (결측이면 percentile/fold 미부착)
    """
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _bucket_for_age(age: float) -> Optional[str]:
    if not _finite(age):
        return None
    a = float(age)
    if a < 19:
        return None
    if a < 30:  return "19-29"
    if a < 40:  return "30-39"
    if a < 50:  return "40-49"
    if a < 60:  return "50-59"
    if a < 70:  return "60-69"
    if a < 80:  return "70-79"
    return "80+"


def compute_percentile(disease: str, age: Optional[float], score: Optional[float]) -> Optional[dict]:
    """
    환자 점수의 동일 연령대 percentile 산출.
    반환: {"percentile": 73, "top_percent": 27, "bucket": "60-69", "n": 1299}
          또는 데이터 없으면 None.
    선형 보간 적용 (p10~p90 사이를 직선 연결).
    """
    if not _finite(score) or not _finite(age):
        return None
    data = _load()
    disease_data = data.get(disease)
    if not disease_data:
        return None
    bucket = _bucket_for_age(age)
    if bucket is None:
        return None  # v2.2.6: age<19/결측 → 적정 코호트 없음 (60-69 오fallback 방지)
    if bucket not in disease_data:
        # 데이터에 해당 버킷이 없을 때만 가장 가까운 성인 버킷으로 fallback
        for fallback in ("60-69", "50-59", "70-79", "40-49"):
            if fallback in disease_data:
                bucket = fallback
                break
        else:
            return None
    stats = disease_data[bucket]

    boundaries = []
    for p in range(10, 100, 10):
        key = f"p{p}"
        if key in stats:
            boundaries.append((p, float(stats[key])))
    if len(boundaries) < 2:
        return None
    boundaries.sort(key=lambda x: x[0])

    s = float(score)

    # 1) score <= p10
    p_low, s_low = boundaries[0]
    if s <= s_low:
        pct = max(1, int(round(p_low * s / s_low))) if s_low > 0 else 1
        return {"percentile": pct, "top_percent": 100 - pct, "bucket": bucket, "n": stats.get("n", 0)}

    # 2) score >= p90
    p_hi, s_hi = boundaries[-1]
    if s >= s_hi:
        # p90~p99 사이는 linear extrapolation. 단 99 로 clamp.
        # 폭은 s_hi 의 20% 정도로 가정.
        denom = max(0.1, s_hi * 0.2)
        extra = (s - s_hi) / denom * (99 - p_hi)
        pct = min(99, int(round(p_hi + extra)))
        return {"percentile": pct, "top_percent": 100 - pct, "bucket": bucket, "n": stats.get("n", 0)}

    # 3) p10 ~ p90 사이 선형 보간
    for i in range(len(boundaries) - 1):
        p1, s1 = boundaries[i]
        p2, s2 = boundaries[i + 1]
        if s1 <= s <= s2:
            if s2 == s1:
                pct = p1
            else:
                pct = int(round(p1 + (s - s1) / (s2 - s1) * (p2 - p1)))
            return {"percentile": pct, "top_percent": 100 - pct, "bucket": bucket, "n": stats.get("n", 0)}
    return None


def compute_fold_change(disease: str, age: Optional[float], score: Optional[float]) -> Optional[dict]:
    """
    환자 점수가 동일 연령대 코호트의 median (p50) 대비 몇 배인지 산출.
    반환: {"fold": 1.5, "bucket": "60-69", "n": 1299}
          - fold > 1.0: 평균보다 위험 높음
          - fold < 1.0: 평균보다 위험 낮음
          - 데이터 없으면 None
    """
    if not _finite(score) or not _finite(age):
        return None
    data = _load()
    disease_data = data.get(disease)
    if not disease_data:
        return None
    bucket = _bucket_for_age(age)
    if bucket is None:
        return None  # v2.2.6: age<19/결측 → 적정 코호트 없음
    if bucket not in disease_data:
        for fallback in ("60-69", "50-59", "70-79", "40-49"):
            if fallback in disease_data:
                bucket = fallback
                break
        else:
            return None
    stats = disease_data[bucket]
    median = stats.get("p50")
    if median is None or median <= 0:
        return None
    fold = float(score) / float(median)
    return {
        "fold": round(fold, 2),
        "bucket": bucket,
        "n": stats.get("n", 0),
        "median": round(float(median), 1),
    }


def enrich_predictions(predictions: dict, age: Optional[float]) -> dict:
    """
    predict_all() 의 결과 dict 의 각 합병증에 percentile/fold 정보를 in-place 로 주입.
    """
    if not _finite(age):
        return predictions
    for key, info in predictions.items():
        if not isinstance(info, dict):
            continue
        if not info.get("available"):
            continue
        score = info.get("score")
        pct = compute_percentile(key, age, score)
        if pct:
            info["percentile"] = pct
        fold = compute_fold_change(key, age, score)
        if fold:
            info["fold_change"] = fold
    return predictions


def available() -> bool:
    """percentile JSON 이 로드되었는지."""
    return bool(_load())
