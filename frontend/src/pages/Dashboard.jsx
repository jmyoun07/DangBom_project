import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowRight, GitCompare, Activity as ActivityIcon, RotateCw } from 'lucide-react';
import api from '../api/client';
import RiskGauge from '../components/RiskGauge';
import RiskCard from '../components/RiskCard';
import TrendChart from '../components/TrendChart';
import usePatientCount from '../hooks/usePatientCount';
import EmptyState from '../components/EmptyState';
import {
  RISK_LEVELS,
  scoreToLevel,
  UNITS,
  prodSafeError,
} from '../theme';
import {
  complicationCards, modelNameMap, topRiskFactor, calcEGFR, buildFactorVal,
} from '../utils/riskDisplay';

// 레벨별 게이지 부제 (고위험/중위험/저위험/평가중 에 따라 다른 문구)
function gaugeSubtitle(level) {
  switch (level) {
    case RISK_LEVELS.HIGH:
      return '\uD569\uBCD1\uC99D \uBC1C\uC0DD \uAC00\uB2A5\uC131\uC774 \uB9E4\uC6B0 \uB192\uC74C\uC73C\uB85C \uC2DD\uBCC4\uB418\uC5C8\uC2B5\uB2C8\uB2E4.';
    case RISK_LEVELS.MID:
      return '\uD569\uBCD1\uC99D \uBC1C\uC0DD \uC704\uD5D8\uC774 \uC911\uAC04 \ub2e8\uACC4\uC785\uB2C8\uB2E4. \uC815\uAE30 \uAD00\ucc30\uC774 \ud544\uc694\ud569\ub2c8\ub2e4.';
    case RISK_LEVELS.LOW:
      return '\ud604\uc7ac \uc8fc\uc694 \ud569\ubcd1\uc99d \uc704\ud5d8\uc774 \ub0ae\uac8c \ud3c9\uac00\ub418\uc5c8\uc2b5\ub2c8\ub2e4.';
    default:
      return 'AI \ubd84\uc11d \uc900\ube44\uac00 \uc644\ub8cc\ub418\ub294 \uB300\ub85c \uD568\uaed8 \ud45c\uc2dc\ub429\ub2c8\ub2e4.';
  }
}

function gaugeHeadingColor(level) {
  // WCAG AA: small bold (14px) requires 4.5:1 contrast on white.
  // text-amber-600 (3.84:1) / emerald-600 (3.94:1) → 700 으로 강화.
  switch (level) {
    case RISK_LEVELS.HIGH: return 'text-red-600';     // 5.7:1
    case RISK_LEVELS.MID:  return 'text-amber-700';   // 5.5:1
    case RISK_LEVELS.LOW:  return 'text-emerald-700'; // 5.4:1
    default:               return 'text-gray-600';    // 7.6:1
  }
}

function gaugeHeading(level) {
  switch (level) {
    case RISK_LEVELS.HIGH: return '\uD569\uBCD1\uC99D \uACE0\uC704\uD5D8 \uB2E8\uACC4';
    case RISK_LEVELS.MID:  return '\uD569\uBCD1\uC99D \uC911\uC704\uD5D8 \uB2E8\uACC4';
    case RISK_LEVELS.LOW:  return '\uD569\uBCD1\uC99D \uC800\uC704\uD5D8 \uB2E8\uACC4';
    default:               return 'AI \ud3c9\uac00 \uC900\uBE44 \uC911';
  }
}

// v2.1.2 — 뒤로가기는 이전 페이지 (PatientList 페이지번호 보존). history 없으면 /patients 로 fallback.
function goBackToList(navigate) {
  if (window.history.length > 1) {
    navigate(-1);
  } else {
    navigate('/patients');
  }
}

export default function Dashboard() {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const { count, loading: countLoading } = usePatientCount();
  const [patient, setPatient] = useState(null);
  const [predictions, setPredictions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [errorKind, setErrorKind] = useState(null); // 'not_found' | 'network' | 'unknown'
  const [predError, setPredError] = useState(null);
  const [predLoading, setPredLoading] = useState(false);

  // patientId 가 유효한 양의 정수인지 (route param 안전성)
  const numericPatientId = Number(patientId);
  const validPatientId = Number.isFinite(numericPatientId) && numericPatientId > 0;

  // patientId 변경 시 이전 환자 잔존 상태 초기화 (스테일 데이터 표시 방지)
  useEffect(() => {
    setPatient(null);
    setPredictions(null);
    setError(null);
    setErrorKind(null);
    setPredError(null);
  }, [patientId]);

  // 응답 레이스 가드 — 환자 빠르게 전환 시 이전 요청의 늦은 응답이 새 환자 화면을 덮지 않도록.
  //   (CaseComparison 의 cancelled 플래그와 동일 목적. 재시도 버튼에서도 호출되므로 seq 방식 사용)
  const loadSeqRef = useRef(0);
  const predSeqRef = useRef(0);

  // 환자 상세 불러오기
  const loadPatient = useCallback(async () => {
    if (!validPatientId) {
      setLoading(false);
      setError('\uC798\ubabb\ub41c \ud658\uc790 ID \uacbd\ub85c\uc785\ub2c8\ub2e4.');
      setErrorKind('not_found');
      return;
    }
    const seq = ++loadSeqRef.current;
    const stale = () => seq !== loadSeqRef.current;
    try {
      setLoading(true);
      setError(null);
      setErrorKind(null);
      const res = await api.get(`/patients/${numericPatientId}`);
      if (stale()) return;
      const d = res.data.data;
      setPatient({ ...(d.patient || d), measurements: d.measurements || [] });
    } catch (err) {
      if (stale()) return;
      prodSafeError('Dashboard.loadPatient')(err);
      const status = err?.response?.status;
      if (status === 404) {
        setError('\ud574\ub2f9 \ud658\uc790\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uc0ad\uc81c\ub418\uc5c8\uac70\ub098 ID\uac00 \uc798\ubabb\ub41c \uacbd\ub85c\uc785\ub2c8\ub2e4.');
        setErrorKind('not_found');
      } else if (!err?.response) {
        setError('\uc11c\ubc84\uc5d0 \uc5f0\uacb0\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uB124\ud2b8\uc6cc\ud06c \uc0c1\ud0dc\ub97c \ud655\uc778\ud558\uc138\uc694.');
        setErrorKind('network');
      } else {
        setError('\ud658\uc790 \ub370\uc774\ud130\ub97c \ubd88\ub7ec\uc62c \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.');
        setErrorKind('unknown');
      }
    } finally {
      if (!stale()) setLoading(false);
    }
  }, [numericPatientId, validPatientId]);

  // 예측 불러오기 (독립 — 예측 실패해도 환자 정보는 표시)
  const runPrediction = useCallback(async () => {
    if (!validPatientId) {
      setPredLoading(false);
      return;
    }
    const seq = ++predSeqRef.current;
    const stale = () => seq !== predSeqRef.current;
    try {
      setPredLoading(true);
      setPredError(null);
      const res = await api.post('/predict', { patient_id: numericPatientId });
      if (stale()) return;
      setPredictions(res.data.data);
    } catch (err) {
      if (stale()) return;
      prodSafeError('Dashboard.predict')(err);
      setPredError('AI \uc608\uce21 \uc11c\ubc84\uc5d0 \uc77c\uc2dc\uc801 \uBB38\uC81C\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.');
    } finally {
      if (!stale()) setPredLoading(false);
    }
  }, [numericPatientId, validPatientId]);

  useEffect(() => {
    if (countLoading || count === 0) return;
    if (!validPatientId) {
      // 잘못된 라우트 → 즉시 에러 표시 (무한 스피너 방지)
      setLoading(false);
      setError('\uC798\ubabb\ub41c \ud658\uc790 ID \uacbd\ub85c\uc785\ub2c8\ub2e4.');
      setErrorKind('not_found');
      return;
    }
    loadPatient();
    runPrediction();
  }, [countLoading, count, validPatientId, loadPatient, runPrediction]);

  if (countLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent" role="status" aria-label="\ub85c\ub529 \uc911" />
      </div>
    );
  }

  if (count === 0) {
    return (
      <EmptyState
        title={'\uB4F1\uB85D\uB41C \uD658\uC790\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4'}
        message={'\uB300\uC2DC\uBCF4\uB4DC\uB294 \uD658\uC790 \uB370\uC774\uD130\uB97C \uAE30\uBC18\uC73C\uB85C \uD45C\uC2DC\uB429\uB2C8\uB2E4. CSV \uD30C\uC77C\uC744 \uC5C5\uB85C\uB4DC\uD55C \uB4A4 \uD658\uC790 \uBAA9\uB85D\uC5D0\uC11C \uC120\uD0DD\uD574 \uC8FC\uC138\uC694.'}
      />
    );
  }

  // 잘못된 patientId → 무한 스피너 대신 명시적 안내
  if (!validPatientId) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <AlertTriangle size={40} className="text-amber-400" aria-hidden="true" />
        <p className="text-gray-700 text-sm">{'\uC798\ubabb\ub41c \ud658\uc790 ID \uacbd\ub85c\uc785\ub2c8\ub2e4.'}</p>
        <Link to="/patients" className="mt-1 inline-flex items-center gap-1 text-sm text-accent hover:underline">
          {'\ud658\uc790 \ubaa9\ub85d\uc5d0\uc11c \uc120\ud0dd\ud558\uae30'} <ArrowRight size={14} />
        </Link>
      </div>
    );
  }

  if (loading && !patient) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent" role="status" aria-label="\ud658\uc790 \uc815\ubcf4 \ub85c\ub529 \uc911" />
      </div>
    );
  }

  if (error || !patient) {
    const isNotFound = errorKind === 'not_found';
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <AlertTriangle size={40} className={isNotFound ? 'text-amber-400' : 'text-red-400'} aria-hidden="true" />
        <p className={`text-sm ${isNotFound ? 'text-gray-700' : 'text-red-500'}`}>
          {error || '\uD658\uC790 \uB370\uC774\uD130\uB97C \uBD88\uB7EC\uC62C \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.'}
        </p>
        {!isNotFound && (
          <button
            onClick={loadPatient}
            className="mt-2 inline-flex items-center gap-1 text-sm text-accent hover:underline"
          >
            <RotateCw size={14} /> {'\ub2e4\uc2dc \uc2dc\ub3c4'}
          </button>
        )}
        <button onClick={() => goBackToList(navigate)} className="text-xs text-gray-500 hover:underline">{'\ud658\uc790 \ubaa9\ub85d\uc73c\ub85c'}</button>
      </div>
    );
  }

  const p = patient;
  const measurements = p.measurements || [];

  // Highest available risk — 예측 성공 시만. 실패/분석중 시 null.
  // v2.1.3 (Codex 리뷰 반영): backend 가 임상 안전망 / 모델 threshold 로 결정한 `level` 을 우선.
  // 단순히 score max 로 등급 재계산하면 권선호 (HbA1c 13.9%, score=1.4 → backend 중위험인데
  // scoreToLevel(1.4) = 저위험) 같은 케이스에서 게이지가 잘못 표시됨.
  const availablePreds = predictions
    ? Object.entries(predictions).filter(([, v]) => v.available && v.score !== null)
    : [];
  // 등급 우선순위 — 고위험 > 중위험 > 저위험. 동급일 때만 score 로 tie-break.
  const LEVEL_RANK = { '고위험': 3, '중위험': 2, '저위험': 1 };
  const highestRisk = availablePreds.length > 0
    ? availablePreds.reduce((max, curr) => {
        const maxRank = LEVEL_RANK[max[1].level] || 0;
        const currRank = LEVEL_RANK[curr[1].level] || 0;
        if (currRank > maxRank) return curr;
        if (currRank < maxRank) return max;
        // 동급 — score 로 tie-break
        return (curr[1].score || 0) > (max[1].score || 0) ? curr : max;
      })
    : null;

  // 예측 불명 시 → score 0, level = null (RiskGauge 는 "평가 중" 회색 표시)
  // backend `level` 우선 사용 (모델 threshold + safety floor 이미 반영됨). 없을 때만 scoreToLevel fallback.
  const overallScore = highestRisk ? (highestRisk[1].display_score ?? highestRisk[1].score) : 0;
  const overallLevel = highestRisk
    ? (highestRisk[1].level || scoreToLevel(highestRisk[1].score))
    : null;

  // v2.2.8 (병원 정책): 필수 검사 누락으로 6개 전부 예측 불가면 게이지/카드에 '데이터 부족' 표시.
  const predList = predictions ? Object.values(predictions) : [];
  const allInsufficient = predList.length > 0 && predList.every((v) => v?.risk_source === 'insufficient_data');
  const insufficientMissing = allInsufficient ? (predList[0]?.missing_required || []) : [];

  // 당화혈색소(HbA1c) 추이 데이터 (병원 피드백: 가장 기본 지표라 좌하단 차트를 HbA1c 로)
  const ymd = (v) => {
    const d = new Date(v);
    return `${String(d.getFullYear()).slice(2)}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  };
  const hba1cTrendData = measurements.map((m) => ({
    month: ymd(m.measured_at),
    value: m.hba1c,
  }));

  // v2.2.7 (F2): 백엔드 단일소스 eGFR(p.egfr, normalize_sex 적용) 우선 — 모델/PatientDetail 과 일치.
  //   클라이언트 calcEGFR 은 백엔드 미산출 시에만 fallback.
  const egfr = (p.egfr != null && p.egfr !== '') ? Math.round(p.egfr) : calcEGFR(p.cr, p.age, p.sex);

  // 항목3: 위험도 1위 합병증의 주요 영향 지표 (휴리스틱, 설명용)
  const factorVal = buildFactorVal(p, egfr);
  const topFactor = highestRisk ? topRiskFactor(highestRisk[0], factorVal) : null;
  const topFactorDisease = highestRisk
    ? (complicationCards.find((c) => modelNameMap[c.type] === highestRisk[0])?.name || '')
    : '';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 fade-in w-full break-keep">
      {/* LEFT COLUMN */}
      <div className="lg:col-span-3 space-y-4 min-w-0">
        {/* 환자 요약 수치 (신원정보는 상단 바에 있으므로 제외) */}
        <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-gray-50 rounded-lg p-2.5 text-center">
              <p className="text-[10px] text-gray-400">HbA1c</p>
              <p className="text-sm font-bold text-gray-800">{p.hba1c ?? '--'}{UNITS.percent}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5 text-center">
              <p className="text-[10px] text-gray-400">{'혈압'}</p>
              <p className="text-sm font-bold text-gray-800">{p.sbp ?? '--'}/{p.dbp ?? '--'}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5 text-center">
              <p className="text-[10px] text-gray-400">{'당뇨 이환기간'}</p>
              <p className="text-sm font-bold text-gray-800">{p.dm_duration ?? '--'}{'년'}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5 text-center">
              <p className="text-[10px] text-gray-400">{'최근 검사일'}</p>
              <p className="text-sm font-bold text-gray-800">
                {(p.exam_date || p.upload_date)
                  ? new Date(p.exam_date || p.upload_date).toLocaleDateString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit' })
                  : '--'}
              </p>
            </div>
          </div>
        </div>

        {/* Critical Status Gauge — 레벨별 동적 문구/색 */}
        <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className={`text-sm font-bold ${gaugeHeadingColor(overallLevel)}`}>
              {gaugeHeading(overallLevel)}
            </h3>
            {overallLevel === RISK_LEVELS.HIGH && <AlertTriangle size={18} className="text-red-400" aria-hidden="true" />}
          </div>

          {predLoading && !predictions ? (
            <div className="flex items-center justify-center h-32">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent" aria-label="AI \ubd84\uc11d \uc911" />
            </div>
          ) : predError ? (
            <div className="flex flex-col items-center gap-2 py-4 text-center">
              <AlertTriangle size={24} className="text-amber-500" aria-hidden="true" />
              <p className="text-xs text-gray-500">{predError}</p>
              <button
                onClick={runPrediction}
                className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
              >
                <RotateCw size={12} /> {'\ub2e4\uc2dc \uc2dc\ub3c4'}
              </button>
            </div>
          ) : (
            <>
              <RiskGauge score={overallScore} level={overallLevel || (allInsufficient ? RISK_LEVELS.INSUFFICIENT : RISK_LEVELS.PENDING)} />
              <p className="text-xs text-gray-500 text-center mt-2">
                {allInsufficient ? '필수 검사 수치가 없어 위험도를 평가할 수 없습니다.' : gaugeSubtitle(overallLevel)}
              </p>
              {allInsufficient && insufficientMissing.length > 0 && (
                <p className="text-[10px] text-gray-400 text-center mt-1 leading-tight">
                  {'누락: '}{insufficientMissing.slice(0, 5).join(', ')}{insufficientMissing.length > 5 ? ` 외 ${insufficientMissing.length - 5}개` : ''}
                </p>
              )}
              {topFactor && topFactor.abnormal && (
                <div className="mt-3 text-[11px] bg-gray-50 rounded-lg px-3 py-2 leading-relaxed">
                  <p className="text-gray-400 mb-0.5">최고 위험 · {topFactorDisease}</p>
                  <p>
                    <span className="text-gray-500">주요 영향 지표 </span>
                    <span className="font-semibold text-gray-700">{topFactor.label}</span>{' '}
                    <span className="font-bold text-red-500">{topFactor.value}{topFactor.unit}</span>
                    <span className="text-gray-400"> (정상 {topFactor.range})</span>
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* CENTER COLUMN - Complication Cards */}
      <div className="lg:col-span-6 min-w-0">
        <h2 className="text-base font-bold text-gray-800 mb-4">{'\uD569\uBCD1\uC99D \uC608\uCE21 \uC704\uD5D8\uB3C4'}</h2>

        {predError && (
          <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-amber-600" />
              <span className="text-xs text-amber-700">{predError}</span>
            </div>
            <button
              onClick={runPrediction}
              disabled={predLoading}
              className="inline-flex items-center gap-1 text-xs text-amber-700 hover:text-amber-800 disabled:opacity-50"
            >
              <RotateCw size={12} /> {predLoading ? '\uc7ac\uc608\uce21 \uc911...' : '\ub2e4\uc2dc \uc2dc\ub3c4'}
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {complicationCards.map((card) => {
            const modelKey = modelNameMap[card.type];
            const pred = predictions?.[modelKey];
            // 대시보드: 실제 합병증 위험지수(N/100) + 백분위('100명 중 N번째') 표시 (병원 6/13)
            return (
              <RiskCard
                key={card.type}
                type={card.type}
                name={card.name}
                englishName={card.englishName}
                level={pred?.level}
                score={pred?.display_score ?? pred?.score}
                available={pred?.available ?? false}
                percentile={pred?.percentile}
                fold={pred?.fold_change}
                age={p.age}
                clinicalFlags={pred?.clinical_flags}
                modelRole={pred?.model_role}
                insufficient={pred?.risk_source === 'insufficient_data'}
                missingRequired={pred?.missing_required}
                showScore
                showPercentile
              />
            );
          })}
        </div>
      </div>

      {/* RIGHT COLUMN */}
      <div className="lg:col-span-3 space-y-4 min-w-0">
        {/* 당화혈색소(HbA1c) 추이 — 우측 빈 공간 활용 + 첫 화면 노출 */}
        <TrendChart
          data={hba1cTrendData}
          unit={UNITS.percent}
          color="var(--color-accent, #6366f1)"
          title={'당화혈색소 수치 추이'}
        />
        {/* CTA Card — Risk Analysis */}
        <div className="gradient-accent rounded-xl p-5 text-white shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <ActivityIcon size={18} aria-hidden="true" />
            <h3 className="text-sm font-bold">{'\uD569\uBCD1\uC99D \uC704\uD5D8 \uBD84\uC11D'}</h3>
          </div>
          <p className="text-xs text-white/95 mb-4 leading-relaxed">
            {'\uC2DC\uB098\uB9AC\uC624 \uAE30\uBC18 \uC608\uCE21 \uBD84\uC11D\uC73C\uB85C \uD658\uC790\uC758 \uBBF8\uB798 \uD569\uBCD1\uC99D \uC704\uD5D8\uB3C4\uB97C \uD655\uC778\uD558\uC138\uC694.'}
          </p>
          <Link
            to={`/risk-analysis/${patientId}`}
            className="inline-flex items-center gap-1 bg-white text-accent px-4 py-2 rounded-lg text-sm font-semibold hover:bg-white/90 transition-colors"
          >
            Risk Analysis {'\uBC14\uB85C\uAC00\uAE30'} <ArrowRight size={14} />
          </Link>
        </div>

        {/* CTA Card — Case Comparison */}
        <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-accent-soft flex items-center justify-center">
              <GitCompare size={16} className="text-accent" aria-hidden="true" />
            </div>
            <h3 className="text-sm font-bold text-gray-800">{'\uC720\uC0AC \uC0AC\uB840 \uBE44\uAD50'}</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4 leading-relaxed">
            {'\uBE44\uC2B7\uD55C \uD658\uC790\uAC00 \uAD00\uB9AC\uB85C \uAC1C\uC120\uB41C \uC2E4\uC81C \uC0AC\uB840 3\uAC74\uC744 \uD655\uC778\uD558\uC138\uC694.'}
          </p>
          <Link
            to={`/case-comparison/${patientId}`}
            className="inline-flex items-center gap-1 text-accent text-sm font-semibold hover:underline"
          >
            {'\uC0AC\uB840 \uBD84\uC11D \uC2DC\uC791\uD558\uAE30'} <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  );
}
