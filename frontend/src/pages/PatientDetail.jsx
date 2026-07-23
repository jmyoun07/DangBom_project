import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ArrowRight, Activity, Pencil, GitCompare, AlertTriangle, RefreshCw, Info, Printer } from 'lucide-react';
import api, { errorMessage } from '../api/client';
import RiskCard from '../components/RiskCard';
import TrendChart from '../components/TrendChart';
import EditPatientModal from '../components/EditPatientModal';
import PatientAuditCard from '../components/PatientAuditCard';
import { invalidatePatientContextCache } from '../components/layout/PatientContextBar';
import {
  UNITS,
  AVAILABLE_DISEASE_KEYS,
  REFERENCE_RANGES,
  scoreToLevel,
  riskColorFor,
  prodSafeError,
  sexKo,
} from '../theme';
import {
  complicationCards, modelNameMap, diseaseCardMetric,
  riskFactors, riskPct, calcEGFR, buildFactorVal, buildRiskFactorVal,
} from '../utils/riskDisplay';

// ── 한의원 검사 14개 항목 정의 ──────────────────────────────
// v2.2.9 — 참고값/판정 기준의 단일 소스는 theme.js 의 REFERENCE_RANGES.
//   (중성지방 ≤149 정상, LDL ≤129 정상, BMI 저체중 컷 18.5 등 표준 기준으로 정정.
//    GGT ≤50 / ALT ≤40 / AST ≤40 / Cr 0.6–1.2 — 코드 기준과 주석 일치)
const LAB_ITEMS_LEFT = [
  { key: 'hba1c', name: '당화혈색소 (HbA1c)', unit: UNITS.hba1c, ref: REFERENCE_RANGES.hba1c },
  { key: 'c_peptide', name: 'C-peptide', unit: UNITS.cpeptide, ref: REFERENCE_RANGES.c_peptide },
  { key: 'fbg', name: '공복혈당', unit: UNITS.glucose, ref: REFERENCE_RANGES.glucose },
  { key: 'ggt', name: 'GGT', unit: UNITS.ggt, ref: REFERENCE_RANGES.ggt },
  { key: 'alt', name: 'ALT', unit: UNITS.alt, ref: REFERENCE_RANGES.alt },
  { key: 'ast', name: 'AST', unit: UNITS.ast, ref: REFERENCE_RANGES.ast },
  { key: 'cr', name: 'Cr (크레아티닌)', unit: UNITS.cr, ref: REFERENCE_RANGES.cr },
];

const LAB_ITEMS_RIGHT = [
  { key: 'total_cholesterol', name: '총콜레스테롤', unit: UNITS.cholesterol, ref: REFERENCE_RANGES.cholesterol },
  { key: 'triglycerides', name: '중성지방', unit: UNITS.triglyceride, ref: REFERENCE_RANGES.triglyceride },
  { key: 'hdl', name: 'HDL 콜레스테롤', unit: UNITS.hdl, ref: REFERENCE_RANGES.hdl },
  { key: 'ldl', name: 'LDL 콜레스테롤', unit: UNITS.ldl, ref: REFERENCE_RANGES.ldl },
  { key: 'sbp', name: '수축기혈압', unit: UNITS.bp, ref: REFERENCE_RANGES.sbp },
  { key: 'dbp', name: '이완기혈압', unit: UNITS.bp, ref: REFERENCE_RANGES.dbp },
  { key: 'bmi', name: '체질량지수 (BMI)', unit: UNITS.bmi, ref: REFERENCE_RANGES.bmi },
];

const RESULT_COLOR = {
  '\uC815\uC0C1':   'text-emerald-600',
  '\uC8FC\uC758':   'text-amber-600',
  '\uB0AE\uC74C':   'text-blue-600',
  '\uB192\uC74C':   'text-red-600',
  // BMI 4-class (v2.1.2)
  '\uC800\uCCB4\uC911': 'text-blue-600',
  '\uACFC\uCCB4\uC911': 'text-amber-600',
  '\uBE44\uB9CC':   'text-red-600',
};
function LabRow({ item, value }) {
  const result = item.ref?.evaluate ? item.ref.evaluate(value) : '';
  const rangeText = item.ref?.text || '';
  return (
    <tr className="border-b border-gray-50 group">
      <td className="py-2 text-xs text-gray-700">
        <span className="inline-flex items-center gap-1" title={rangeText}>
          {item.name}
          {rangeText && (
            <Info size={11} className="text-gray-300 group-hover:text-gray-400 transition-colors" aria-hidden="true" />
          )}
        </span>
      </td>
      <td className="py-2 text-xs font-semibold text-gray-800 text-right">{value ?? '--'}</td>
      <td className="py-2 text-xs text-gray-400 text-right pl-3">{item.unit}</td>
      <td className={`py-2 text-xs font-semibold text-right pl-4 ${RESULT_COLOR[result] || 'text-gray-400'}`}>
        {result || '--'}
      </td>
    </tr>
  );
}

// ── 예측 캐시 키: 환자 id + 마지막 수정 시각 + 슬림 해시 ──────
// 환자 lab 값이 바뀌지 않았으면 같은 키 → POST 생략.
function predKey(patient) {
  if (!patient) return null;
  const stamp = patient.updated_at || patient.exam_date || patient.upload_date || '';
  return `dbcare:pred:${patient.id}:${stamp}`;
}

// ── 파생/예측 호출 (환자 변경 시에만) ─────────────────────────
async function fetchPrediction(patientId) {
  const res = await api.post('/predict', { patient_id: parseInt(patientId) });
  return res.data.data;
}

// v2.1.2 — 뒤로가기는 이전 페이지 (PatientList 페이지번호 보존). history 없으면 /patients.
function goBackToList(navigate) {
  if (window.history.length > 1) navigate(-1);
  else navigate('/patients');
}

export default function PatientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [patient, setPatient] = useState(null);
  const [measurements, setMeasurements] = useState([]);
  const [predictions, setPredictions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [predError, setPredError] = useState(null);
  const [predLoading, setPredLoading] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  // N2: 환자 수정 후 audit 카드 재조회 트리거
  const [auditRefreshKey, setAuditRefreshKey] = useState(0);

  // 응답 레이스 가드 — 환자 빠르게 전환 시 이전 요청의 늦은 응답이 새 환자 화면을 덮지 않도록.
  //   (CaseComparison 의 cancelled 플래그와 동일 목적. onSaved 재호출도 있어 seq 방식 사용)
  const loadSeqRef = useRef(0);
  const predSeqRef = useRef(0);

  // patientId 변경 시 이전 환자 잔존 상태 초기화 —
  //   초기화 없이는 '새 환자 정보 + 이전 환자 예측' 이 한 화면에 같이 보일 수 있다.
  useEffect(() => {
    setPatient(null);
    setMeasurements([]);
    setPredictions(null);
    setPredError(null);
    setLoading(true);
  }, [id]);

  // ── 환자 기본 정보 로드 (페이지 진입 / id 변경 시) ────────
  const loadPatient = useCallback(async () => {
    const seq = ++loadSeqRef.current;
    const stale = () => seq !== loadSeqRef.current;
    try {
      setLoading(true);
      const patRes = await api.get(`/patients/${id}`);
      if (stale()) return;
      const d = patRes.data.data;
      const pat = d.patient || d;
      setPatient(pat);
      setMeasurements(d.measurements || []);
    } catch (e) {
      if (stale()) return;
      prodSafeError('loadPatient')(e);
      setPatient(null);
    } finally {
      if (!stale()) setLoading(false);
    }
  }, [id]);

  useEffect(() => { loadPatient(); }, [loadPatient]);

  // ── 예측 캐시 로드 또는 신규 호출 ────────────────────────
  // 환자 객체가 준비된 뒤, 캐시 키가 바뀔 때(=편집으로 updated_at 갱신)만 재호출.
  const cacheKey = useMemo(() => predKey(patient), [patient]);

  // I21: onSaved 가 이전 렌더의 runPrediction 클로저를 직접 호출하면 POST /predict 가 중복 실행됨
  //   → ref 에 '다음 예측은 강제' 플래그만 남기고, loadPatient 후 effect 재실행이 최신 키로 예측하게 한다.
  const forceNextPredRef = useRef(false);

  const runPrediction = useCallback(async ({ force = false } = {}) => {
    if (!patient || !cacheKey) return;
    if (String(patient.id) !== String(id)) return; // 환자 전환 직후 이전 환자 객체로 예측 방지
    const useForce = force || forceNextPredRef.current;
    forceNextPredRef.current = false;
    // seq 증가를 캐시 조회보다 먼저 — 캐시 적중으로 early return 하더라도 이전 환자의
    //   in-flight 응답이 stale 판정을 받아 새 캐시 결과를 덮어쓰지 못하게 한다.
    const seq = ++predSeqRef.current;
    const stale = () => seq !== predSeqRef.current;
    if (!useForce) {
      try {
        const cached = sessionStorage.getItem(cacheKey);
        if (cached) {
          setPredictions(JSON.parse(cached));
          setPredError(null);
          setPredLoading(false);
          return;
        }
      } catch { /* storage disabled — ignore */ }
    }
    try {
      setPredLoading(true);
      setPredError(null);
      const pred = await fetchPrediction(id);
      if (stale()) return;
      setPredictions(pred);
      try { sessionStorage.setItem(cacheKey, JSON.stringify(pred)); } catch { /* quota — ignore */ }
    } catch (e) {
      if (stale()) return;
      prodSafeError('predict')(e);
      setPredError(errorMessage(e, '예측 서버에 접속할 수 없습니다.'));
    } finally {
      if (!stale()) setPredLoading(false);
    }
  }, [patient, cacheKey, id]);

  useEffect(() => { runPrediction(); }, [runPrediction]);

  // ── 편집 완료 → 환자 재로드 + 예측 강제 갱신 ─────────────
  //   I21: 이전 렌더 클로저의 runPrediction({force}) 직접 호출 제거 — loadPatient 후 patient/cacheKey 가
  //   갱신되면 effect 가 최신 클로저로 재예측한다 (forceNextPredRef 로 캐시 무시 보장, POST 중복 방지).
  const onSaved = async (updated) => {
    if (updated) setPatient((prev) => ({ ...prev, ...updated }));
    invalidatePatientContextCache(id);  // I1: PatientContextBar 캐시 무효화
    forceNextPredRef.current = true;    // 다음 예측은 세션 캐시 무시하고 강제 재호출
    await loadPatient();                // 최신 updated_at 반영 → effect 가 재예측
    setAuditRefreshKey((k) => k + 1);   // N2: 수정 이력 카드 재조회
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-accent" role="status" aria-label="\ub85c\ub529 \uc911" />
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3 text-center">
        <AlertTriangle size={32} className="text-amber-500" aria-hidden="true" />
        <div className="text-gray-500">{'\uD658\uC790\uB97C \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.'}</div>
        <div className="flex gap-2">
          <button onClick={loadPatient} className="px-3 py-1.5 text-xs border border-gray-200 rounded-md hover:bg-gray-50">
            {'\ub2e4\uc2dc \uc2dc\ub3c4'}
          </button>
          <Link to="/patients" className="px-3 py-1.5 text-xs bg-accent text-white rounded-md">
            {'\ud658\uc790 \ubaa9\ub85d\uc73c\ub85c'}
          </Link>
        </div>
      </div>
    );
  }

  // 병원 피드백: 차트 X축을 '24년 1월'이 아니라 '24.01.02' 정확한 날짜로.
  const ymd = (v) => {
    const d = new Date(v);
    return `${String(d.getFullYear()).slice(2)}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  };
  const cpeptideData = measurements.map(m => ({ month: ymd(m.measured_at), value: m.c_peptide }));
  const hba1cData = measurements.map(m => ({ month: ymd(m.measured_at), value: m.hba1c }));
  const crData = measurements.map(m => ({ month: ymd(m.measured_at), value: m.cr }));

  // 합병증 1순위 요인 카드 + 주요 위험 요인 정리 패널용 (대시보드에서 이동, 병원 6/13)
  const egfr = (patient.egfr != null && patient.egfr !== '') ? Math.round(patient.egfr) : calcEGFR(patient.cr, patient.age, patient.sex);
  const factorVal = buildFactorVal(patient, egfr);
  const riskFactorVal = buildRiskFactorVal(patient, egfr);


  // ML 완성 모델 수 (UI에 정직하게 노출)
  const totalModules = 6;
  const readyModules = AVAILABLE_DISEASE_KEYS.size;

  return (
    <div className="space-y-5 fade-in w-full">
      {/* Top nav */}
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => goBackToList(navigate)} className="flex items-center gap-1 text-sm text-gray-500 hover:text-accent transition-colors mb-2">
            <ChevronLeft size={14} /> {'\uD658\uC790 \uBAA9\uB85D\uC73C\uB85C \uB3CC\uC544\uAC00\uAE30'}
          </button>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">{patient.name} {'\uD658\uC790 \uC0C1\uC138 \uC815\uBCF4'}</h1>
        </div>
        <div className="flex gap-2 print:hidden">
          <button
            onClick={() => setEditOpen(true)}
            className="flex items-center gap-1.5 px-4 py-2 border border-gray-200 text-sm text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <Pencil size={14} />
            {'\uB370\uC774\uD130 \uC218\uC815'}
          </button>
          <Link
            to={`/risk-analysis/${id}`}
            className="flex items-center gap-1.5 px-4 py-2 border border-accent text-accent text-sm font-semibold rounded-lg hover:bg-accent-soft transition-colors"
          >
            <Activity size={14} />
            {'Risk Analysis'}
          </Link>
          <Link
            to={`/case-comparison/${id}`}
            className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white text-sm font-semibold rounded-lg hover:bg-accent-dark transition-colors shadow-sm"
          >
            <GitCompare size={14} />
            {'\uC720\uC0AC \uC0AC\uB840'}
          </Link>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-1.5 px-4 py-2 bg-gray-800 text-white text-sm font-semibold rounded-lg hover:bg-gray-900 transition-colors shadow-sm"
          >
            <Printer size={14} />
            {'\uACB0\uACFC \uB9AC\uD3EC\uD2B8 \uCD9C\uB825'}
          </button>
        </div>
      </div>

      {editOpen && (
        <EditPatientModal
          patient={patient}
          onClose={() => setEditOpen(false)}
          onSaved={onSaved}
        />
      )}

      <div className="grid grid-cols-12 gap-5">
        {/* Left — Basic info */}
        <div className="col-span-3 space-y-4">
          <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
            <div className="flex flex-col items-center text-center mb-5">
              <div className="w-16 h-16 rounded-full bg-accent flex items-center justify-center text-white text-2xl font-bold mb-3 shadow-sm">
                {(patient.name || '?')[0]}
              </div>
              <h2 className="text-base font-bold text-gray-800">{patient.name}</h2>
              <p className="text-xs text-gray-500 mt-1">{patient.chart_no}</p>
            </div>
            <div className="space-y-3 pt-4 border-t border-gray-100">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">{'\uC0DD\uB144\uC6D4\uC77C'}</span>
                <span className="font-medium text-gray-800">{patient.dob || '--'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">{'\uB098\uC774\u00B7\uC131\uBCC4'}</span>
                <span className="font-medium text-gray-800">{patient.age}{UNITS.age} / {sexKo(patient.sex)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">{'\uC5F0\uB77D\uCC98'}</span>
                <span className="font-medium text-gray-800">{patient.phone || '--'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">{'\uCD5C\uADFC \uAC80\uC0AC\uC77C'}</span>
                <span className="font-medium text-gray-800">
                  {(patient.exam_date || patient.upload_date)
                    ? new Date(patient.exam_date || patient.upload_date).toLocaleDateString('ko-KR')
                    : '--'}
                </span>
              </div>
            </div>
          </div>
        <div className="gradient-accent rounded-xl p-5 text-white flex flex-col justify-between shadow-sm">
          <div>
            <Activity size={24} className="mb-2 text-white/90" aria-hidden="true" />
            <h3 className="text-sm font-bold mb-1">{'\uD569\uBCD1\uC99D \uC704\uD5D8 \uBD84\uC11D'}</h3>
            <p className="text-[11px] text-white/95 leading-relaxed">
              {'\uC2DC\uB098\uB9AC\uC624\uB85C \uBBF8\uB798 \uC0C1\uD0DC\uB97C \uC608\uCE21\uD558\uACE0 \uAD8C\uC7A5 \uD504\uB85C\uADF8\uB7A8\uC744 \uD655\uC778\uD558\uC138\uC694.'}
            </p>
          </div>
          <Link
            to={`/risk-analysis/${id}`}
            className="inline-flex items-center gap-1 bg-white text-accent px-3 py-2 rounded-lg text-xs font-semibold hover:bg-white/90 transition-colors mt-3 justify-center"
          >
            Risk Analysis <ArrowRight size={12} aria-hidden="true" />
          </Link>
        </div>
        <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
          <div className="w-9 h-9 rounded-lg bg-accent-soft flex items-center justify-center mb-2">
            <GitCompare size={18} className="text-accent" aria-hidden="true" />
          </div>
          <h3 className="text-sm font-bold text-gray-800 mb-1">{'\uC720\uC0AC \uC0AC\uB840 \uBE44\uAD50'}</h3>
          <p className="text-[11px] text-gray-500 leading-relaxed mb-3">
            {'\uBE44\uC2B7\uD55C \uD658\uC790 \uC0AC\uB840\uC5D0\uC11C \uAC1C\uC120 \uACBD\uB85C\uB97C \uCC3E\uC544\uBD05\uB2C8\uB2E4.'}
          </p>
          <Link
            to={`/case-comparison/${id}`}
            className="inline-flex items-center gap-1 text-accent text-xs font-semibold hover:underline"
          >
            {'\uC0AC\uB840 \uBD84\uC11D \uBCF4\uAE30'} <ArrowRight size={12} aria-hidden="true" />
          </Link>
        </div>

        {/* N2: 수정 이력 카드 */}
        <PatientAuditCard patientId={id} refreshKey={auditRefreshKey} />
        </div>

        {/* Right — AI 예측 + 추이 차트 */}
        <div className="col-span-9 space-y-5">
          {/* 합병증별 1순위 요인 (대시보드에서 이동, 병원 6/13) */}
          <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-800">{'합병증별 1순위 요인'}</h3>
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex items-center gap-1 px-2.5 py-1 bg-accent-soft text-accent text-xs rounded-full font-medium"
                  title={`ML 모델 ${readyModules}개 완성 / 총 ${totalModules}개`}
                >
                  AI {'분석'} {readyModules}/{totalModules} {'모듈'}
                </span>
                {predLoading && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                    <RefreshCw size={12} className="animate-spin" aria-hidden="true" />
                    {'예측 갱신 중'}
                  </span>
                )}
              </div>
            </div>

            {predError && (
              <div className="mb-3 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700">
                <span className="inline-flex items-center gap-1.5">
                  <AlertTriangle size={14} aria-hidden="true" /> {predError}
                </span>
                <button
                  onClick={() => runPrediction({ force: true })}
                  className="inline-flex items-center gap-1 px-2 py-1 border border-red-300 rounded text-red-700 hover:bg-red-100"
                >
                  <RefreshCw size={11} aria-hidden="true" /> {'다시 시도'}
                </button>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {complicationCards.map((card) => {
                const modelKey = modelNameMap[card.type];
                const pred = predictions?.[modelKey];
                const cm = diseaseCardMetric(modelKey, factorVal);
                return (
                  <RiskCard
                    key={card.type}
                    type={card.type}
                    name={card.name}
                    englishName={card.englishName}
                    level={pred?.level}
                    metricLabel={cm ? cm.label : card.metricLabel}
                    metricValue={cm ? `${cm.value}${cm.unit}` : '--'}
                    score={pred?.display_score ?? pred?.score}
                    available={pred?.available ?? false}
                    insufficient={pred?.risk_source === 'insufficient_data'}
                    missingRequired={pred?.missing_required}
                    age={patient.age}
                    clinicalFlags={pred?.clinical_flags}
                    modelRole={pred?.model_role}
                    showPercentile={false}
                  />
                );
              })}
            </div>
          </div>

          {/* 주요 위험 요인 정리 (대시보드에서 이동) */}
          <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
            <h3 className="text-sm font-bold text-gray-800 mb-1">{'주요 위험 요인 정리'}</h3>
            <p className="text-[10px] text-gray-400 mb-4">{'위험도 산출에 영향이 큰 지표 순으로 정렬됩니다.'}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
              {riskFactors
                .map((rf) => { const v = riskFactorVal(rf.key); return { rf, value: v, pct: riskPct(rf.key, v, rf.ref) }; })
                .sort((a, b) => b.pct - a.pct)
                .map(({ rf, value, pct }) => {
                  const lvl = scoreToLevel(pct);
                  const color = riskColorFor(lvl);
                  return (
                    <div key={rf.key} title={`정상: ${rf.normalLabel}`}>
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="text-xs text-gray-500">{rf.label}</span>
                        <span className="text-xs font-semibold text-gray-700">
                          {value ?? '--'} <span className="text-gray-400 font-normal">{rf.unit}</span>
                        </span>
                      </div>
                      <div
                        className="w-full bg-gray-100 rounded-full h-1.5"
                        role="progressbar"
                        aria-valuenow={Math.round(pct)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`${rf.label} ${color.ariaLabel}`}
                      >
                        <div className={`h-1.5 rounded-full transition-all duration-500 ${color.bar}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Trend charts — 색 통일 (accent / amber / emerald — 의미 분리 대신 일관된 accent) */}
          <div className="grid grid-cols-3 gap-4">
            <TrendChart data={cpeptideData} unit={UNITS.cpeptide} color="var(--color-accent, #6366f1)" title="C-peptide" />
            <TrendChart data={hba1cData} unit={UNITS.hba1c} color="var(--color-accent, #6366f1)" title="HbA1c" />
            <TrendChart data={crData} unit={UNITS.cr} color="var(--color-accent, #6366f1)" title={'Cr \uD06C\uB808\uC544\uD2F0\uB2CC'} />
          </div>
        </div>
      </div>

      {/* Lab values (14 items, 2 columns) */}
      <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
          <h3 className="text-sm font-bold text-gray-800 mb-1">{'\uCD5C\uADFC \uAC80\uC0AC \uC218\uCE58'}</h3>
          <p className="text-[11px] text-gray-400 mb-4">
            {'\ud56d\ubaa9 \uc774\ub984 \uc624\ub978\ucabd '} <Info size={10} className="inline text-gray-300 align-middle" aria-hidden="true" /> {'\uc544\uc774\ucf58\uc5d0 \ub9c8\uc6b0\uc2a4\ub97c \uc62c\ub9ac\uba74 \uc815\uc0c1 \ubc94\uc704\ub97c \ubcfc \uc218 \uc788\uc2b5\ub2c8\ub2e4.'}
          </p>
          <div className="grid grid-cols-2 gap-6">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left text-[10px] text-gray-500 uppercase pb-2">{'\uD56D\uBAA9'}</th>
                  <th className="text-right text-[10px] text-gray-500 uppercase pb-2">{'\uC218\uCE58'}</th>
                  <th className="text-right text-[10px] text-gray-500 uppercase pb-2 pl-3">{'\uB2E8\uC704'}</th>
                  <th className="text-right text-[10px] text-gray-500 uppercase pb-2 pl-4">{'\uBE44\uACE0'}</th>
                </tr>
              </thead>
              <tbody>
                {LAB_ITEMS_LEFT.map((item) => (
                  <LabRow key={item.key} item={item} value={patient[item.key]} />
                ))}
              </tbody>
            </table>

            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left text-[10px] text-gray-500 uppercase pb-2">{'\uD56D\uBAA9'}</th>
                  <th className="text-right text-[10px] text-gray-500 uppercase pb-2">{'\uC218\uCE58'}</th>
                  <th className="text-right text-[10px] text-gray-500 uppercase pb-2 pl-3">{'\uB2E8\uC704'}</th>
                  <th className="text-right text-[10px] text-gray-500 uppercase pb-2 pl-4">{'\uBE44\uACE0'}</th>
                </tr>
              </thead>
              <tbody>
                {LAB_ITEMS_RIGHT.map((item) => (
                  <LabRow key={item.key} item={item} value={patient[item.key]} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
    </div>
  );
}
