import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ArrowRight, Activity, Pencil, GitCompare, AlertTriangle, RefreshCw, Info } from 'lucide-react';
import api from '../api/client';
import RiskBadge from '../components/RiskBadge';
import RiskBar from '../components/RiskBar';
import TrendChart from '../components/TrendChart';
import EditPatientModal from '../components/EditPatientModal';
import PatientAuditCard from '../components/PatientAuditCard';
import { invalidatePatientContextCache } from '../components/layout/PatientContextBar';
import {
  UNITS,
  REFERENCE_RANGES,
  MODEL_META,
  AVAILABLE_DISEASE_KEYS,
  prodSafeError,
} from '../theme';

// ── \uD55C\uC758\uC6D0 \uAC80\uC0AC 14\uAC1C \uD56D\uBAA9 \uC815\uC758 ──────────────────────────────
// v2.1.2 — \uC815\uC0C1\uBC94\uC704 \uC784\uC0C1 \uAE30\uC900 \uAC31\uC2E0:
//   HDL 40-75 / C-peptide 1.0-3.5 / GGT 0-66 / ALT 0-45 / AST 0-40
//   Cr 0.5-1.3 / CHOL 120-230 / Trig 0-200 / LDL 0-130
//   BMI: <19 \uC800\uCCB4\uC911 / 19-22.9 \uC815\uC0C1 / 23-24.9 \uACFC\uCCB4\uC911 / >=25 \uBE44\uB9CC
const LAB_ITEMS_LEFT = [
  { key: 'hba1c', name: '\uB2F9\uD654\uD608\uC0C9\uC18C (HbA1c)', unit: UNITS.hba1c, range: '<= 5.6 \uC815\uC0C1 / 5.7-6.4 \uC8FC\uC758 / >= 6.5 \uB2F9\uB1E8',
    evaluate: (v) => v == null ? '' : v <= 5.6 ? '\uC815\uC0C1' : v <= 6.4 ? '\uC8FC\uC758' : '\uB192\uC74C' },
  { key: 'c_peptide', name: 'C-peptide', unit: UNITS.cpeptide, range: '1.0 - 3.5 ng/mL',
    evaluate: (v) => v == null ? '' : (v >= 1.0 && v <= 3.5) ? '\uC815\uC0C1' : v < 1.0 ? '\uB0AE\uC74C' : '\uB192\uC74C' },
  { key: 'fbg', name: '\uACF5\uBCF5\uD608\uB2F9', unit: UNITS.glucose, range: '70-99 \uC815\uC0C1 / 100-125 \uC8FC\uC758 / >=126 \uB2F9\uB1E8',
    evaluate: (v) => v == null ? '' : v <= 99 ? '\uC815\uC0C1' : v <= 125 ? '\uC8FC\uC758' : '\uB192\uC74C' },
  { key: 'ggt', name: 'GGT', unit: UNITS.ggt, range: '0 - 66 U/L',
    evaluate: (v) => v == null ? '' : v <= 66 ? '\uC815\uC0C1' : '\uB192\uC74C' },
  { key: 'alt', name: 'ALT', unit: UNITS.alt, range: '0 - 45 U/L',
    evaluate: (v) => v == null ? '' : v <= 45 ? '\uC815\uC0C1' : '\uB192\uC74C' },
  { key: 'ast', name: 'AST', unit: UNITS.ast, range: '0 - 40 U/L',
    evaluate: (v) => v == null ? '' : v <= 40 ? '\uC815\uC0C1' : '\uB192\uC74C' },
  { key: 'cr', name: 'Cr (\uD06C\uB808\uC544\uD2F0\uB2CC)', unit: UNITS.cr, range: '0.5 - 1.3 mg/dL',
    evaluate: (v) => v == null ? '' : (v >= 0.5 && v <= 1.3) ? '\uC815\uC0C1' : v < 0.5 ? '\uB0AE\uC74C' : '\uB192\uC74C' },
];

const LAB_ITEMS_RIGHT = [
  { key: 'total_cholesterol', name: '\uCD1D\uCF5C\uB808\uC2A4\uD14C\uB864', unit: UNITS.cholesterol, range: '120 - 230 mg/dL',
    evaluate: (v) => v == null ? '' : (v >= 120 && v <= 230) ? '\uC815\uC0C1' : v < 120 ? '\uB0AE\uC74C' : '\uB192\uC74C' },
  { key: 'triglycerides', name: '\uC911\uC131\uC9C0\uBC29', unit: UNITS.triglyceride, range: '0 - 200 mg/dL',
    evaluate: (v) => v == null ? '' : v <= 200 ? '\uC815\uC0C1' : '\uB192\uC74C' },
  { key: 'hdl', name: 'HDL \uCF5C\uB808\uC2A4\uD14C\uB864', unit: UNITS.hdl, range: '40 - 75 mg/dL',
    evaluate: (v) => v == null ? '' : (v >= 40 && v <= 75) ? '\uC815\uC0C1' : v < 40 ? '\uB0AE\uC74C' : '\uB192\uC74C' },
  { key: 'ldl', name: 'LDL \uCF5C\uB808\uC2A4\uD14C\uB864', unit: UNITS.ldl, range: '0 - 130 mg/dL',
    evaluate: (v) => v == null ? '' : v <= 130 ? '\uC815\uC0C1' : '\uB192\uC74C' },
  { key: 'sbp', name: '\uC218\uCD95\uAE30\uD608\uC555', unit: UNITS.bp, range: '<=119 \uC815\uC0C1 / 120-139 \uC8FC\uC758 / >=140 \uB192\uC74C',
    evaluate: (v) => v == null ? '' : v <= 119 ? '\uC815\uC0C1' : v <= 139 ? '\uC8FC\uC758' : '\uB192\uC74C' },
  { key: 'dbp', name: '\uC774\uC644\uAE30\uD608\uC555', unit: UNITS.bp, range: '<=79 \uC815\uC0C1 / 80-89 \uC8FC\uC758 / >=90 \uB192\uC74C',
    evaluate: (v) => v == null ? '' : v <= 79 ? '\uC815\uC0C1' : v <= 89 ? '\uC8FC\uC758' : '\uB192\uC74C' },
  { key: 'bmi', name: '\uCCB4\uC9C8\uB7C9\uC9C0\uC218 (BMI)', unit: UNITS.bmi, range: '<19 \uC800\uCCB4\uC911 / 19-22.9 \uC815\uC0C1 / 23-24.9 \uACFC\uCCB4\uC911 / >=25 \uBE44\uB9CC',
    evaluate: (v) => v == null ? '' : v < 19 ? '\uC800\uCCB4\uC911' : v <= 22.9 ? '\uC815\uC0C1' : v <= 24.9 ? '\uACFC\uCCB4\uC911' : '\uBE44\uB9CC' },
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
  const result = item.evaluate(value);
  return (
    <tr className="border-b border-gray-50 group">
      <td className="py-2 text-xs text-gray-700">
        <span className="inline-flex items-center gap-1" title={item.range || ''}>
          {item.name}
          {item.range && (
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

  // ── 환자 기본 정보 로드 (페이지 진입 / id 변경 시) ────────
  const loadPatient = useCallback(async () => {
    try {
      setLoading(true);
      const patRes = await api.get(`/patients/${id}`);
      const d = patRes.data.data;
      const pat = d.patient || d;
      setPatient(pat);
      setMeasurements(d.measurements || []);
    } catch (e) {
      prodSafeError('loadPatient')(e);
      setPatient(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { loadPatient(); }, [loadPatient]);

  // ── 예측 캐시 로드 또는 신규 호출 ────────────────────────
  // 환자 객체가 준비된 뒤, 캐시 키가 바뀔 때(=편집으로 updated_at 갱신)만 재호출.
  const cacheKey = useMemo(() => predKey(patient), [patient]);

  const runPrediction = useCallback(async ({ force = false } = {}) => {
    if (!patient || !cacheKey) return;
    if (!force) {
      try {
        const cached = sessionStorage.getItem(cacheKey);
        if (cached) {
          setPredictions(JSON.parse(cached));
          setPredError(null);
          return;
        }
      } catch { /* storage disabled — ignore */ }
    }
    try {
      setPredLoading(true);
      setPredError(null);
      const pred = await fetchPrediction(id);
      setPredictions(pred);
      try { sessionStorage.setItem(cacheKey, JSON.stringify(pred)); } catch { /* quota — ignore */ }
    } catch (e) {
      prodSafeError('predict')(e);
      setPredError(e?.response?.data?.detail || '\uC608\uCE21 \uC11C\ubc84\uc5d0 \uc811\uc18d\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.');
    } finally {
      setPredLoading(false);
    }
  }, [patient, cacheKey, id]);

  useEffect(() => { runPrediction(); }, [runPrediction]);

  // ── 편집 완료 → 환자 재로드 + 예측 강제 갱신 ─────────────
  const onSaved = async (updated) => {
    if (updated) setPatient((prev) => ({ ...prev, ...updated }));
    invalidatePatientContextCache(id);  // I1: PatientContextBar 캐시 무효화
    await loadPatient();                // 최신 updated_at 반영
    await runPrediction({ force: true }); // 예측 강제 재호출
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

  const cpeptideData = measurements.map(m => ({
    month: new Date(m.measured_at).toLocaleDateString('ko-KR', { year: '2-digit', month: 'short' }),
    value: m.c_peptide,
  }));
  const hba1cData = measurements.map(m => ({
    month: new Date(m.measured_at).toLocaleDateString('ko-KR', { year: '2-digit', month: 'short' }),
    value: m.hba1c,
  }));
  const crData = measurements.map(m => ({
    month: new Date(m.measured_at).toLocaleDateString('ko-KR', { year: '2-digit', month: 'short' }),
    value: m.cr,
  }));

  // v2.1.7 \u2014 6\uAC1C \uBAA8\uB378 \uD1B5\uD569. \uC2E0\uADDC 3\uAC1C\uB294 usage_warning \uC73C\uB85C SCREENING/PROTOTYPE \uACBD\uACE0 \uD45C\uC2DC.
  const completedModels = [
    { key: 'kidney_disease',   metaKey: 'kidney',   name: '\uB2F9\uB1E8\uBCD1\uC131 \uC2E0\uC7A5\uC9C8\uD658' },
    { key: 'retinopathy',      metaKey: 'retina',   name: '\uB2F9\uB1E8\uBCD1\uC131 \uB9DD\uB9C9\uBCD1\uC99D' },
    { key: 'cardiovascular',   metaKey: 'cardio',   name: '\uB2F9\uB1E8\uBCD1\uC131 \uC2EC\uD608\uAD00 \uC9C8\uD658' },
    { key: 'neuropathy',       metaKey: 'neuro',    name: '\uB2F9\uB1E8\uBCD1\uC131 \uC2E0\uACBD\uBCD1\uC99D' },
    { key: 'dementia',         metaKey: 'dementia', name: '\uB2F9\uB1E8\uBCD1\uC131 \uCE58\uB9E4' },
    { key: 'cerebrovascular',  metaKey: 'cerebro',  name: '\uB2F9\uB1E8\uBCD1\uC131 \uB1CC\uD608\uAD00 \uC9C8\uD658' },
  ];

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
        <div className="flex gap-2">
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
        <div className="col-span-3">
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
                <span className="font-medium text-gray-800">{patient.age}{UNITS.age} / {patient.sex === 'M' ? '\uB0A8' : '\uC5EC'}</span>
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
        </div>

        {/* Right — AI 예측 + 추이 차트 */}
        <div className="col-span-9 space-y-5">
          {/* AI Predictions */}
          <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-800">AI {'\uD569\uBCD1\uC99D \uC608\uCE21 \uACB0\uACFC'}</h3>
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex items-center gap-1 px-2.5 py-1 bg-accent-soft text-accent text-xs rounded-full font-medium"
                  title={`ML \ubaa8\ub378 ${readyModules}\uac1c \uc644\uc131 / \ucd5d ${totalModules}\uac1c \ud569\ubcd1\uc99d \uc608\uce21 \ubaa9\ud45c`}
                >
                  AI {'\uBD84\uC11D'} {readyModules}/{totalModules} {'\ubaa8\ub4c8'}
                </span>
                {predLoading && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                    <RefreshCw size={12} className="animate-spin" aria-hidden="true" />
                    {'\uc608\uce21 \uac31\uc2e0 \uc911'}
                  </span>
                )}
              </div>
            </div>

            {/* 예측 실패 시 재시도 */}
            {predError && (
              <div className="mb-3 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700">
                <span className="inline-flex items-center gap-1.5">
                  <AlertTriangle size={14} aria-hidden="true" /> {predError}
                </span>
                <button
                  onClick={() => runPrediction({ force: true })}
                  className="inline-flex items-center gap-1 px-2 py-1 border border-red-300 rounded text-red-700 hover:bg-red-100"
                >
                  <RefreshCw size={11} aria-hidden="true" /> {'\ub2e4\uc2dc \uc2dc\ub3c4'}
                </button>
              </div>
            )}

            <div className="grid grid-cols-3 gap-3">
              {completedModels.map((m) => {
                const pred = predictions?.[m.key];
                const meta = MODEL_META[m.metaKey];
                if (!pred?.available) {
                  return (
                    <div key={m.key} className="bg-gray-50 rounded-lg p-3 opacity-70">
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-xs font-medium text-gray-700">{m.name}</span>
                        <RiskBadge level={null} />
                      </div>
                      <p className="text-[11px] text-gray-400">{'\uc608\uce21 \uac12 \uc5c6\uc74c'}</p>
                    </div>
                  );
                }
                return (
                  <div key={m.key} className="bg-gray-50 rounded-lg p-3">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-xs font-medium text-gray-700">{m.name}</span>
                      <RiskBadge level={pred.level} />
                    </div>
                    <p className="text-xs text-gray-500 mb-1">
                      {'\uC704\uD5D8\uC9C0\uC218'} <span className="text-sm font-bold text-gray-800">{pred.score}</span>/100
                    </p>
                    <RiskBar score={pred.score} level={pred.level} />
                    {meta && (
                      <div
                        className="mt-2 text-[10px] text-gray-400 truncate"
                        title={`${meta.algorithm} / cohort ${meta.cohort} / ${meta.nFeatures} features`}
                      >
                        {meta.algorithmShort || meta.algorithm}
                      </div>
                    )}
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
      <div className="grid grid-cols-3 gap-5">
        <div className="col-span-2 bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
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

        {/* CTA stack */}
        <div className="space-y-4">
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
      </div>
    </div>
  );
}
