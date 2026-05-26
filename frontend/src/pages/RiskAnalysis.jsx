import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { RotateCcw, AlertCircle, Zap, ArrowRight, Lightbulb, Loader2, GraduationCap } from 'lucide-react';
import api from '../api/client';
import RadarChart from '../components/RadarChart';
import useDebounce from '../hooks/useDebounce';
import usePatientCount from '../hooks/usePatientCount';
import EmptyState from '../components/EmptyState';
import {
  RISK_LEVELS,
  riskColorFor,
  DISEASE_LABELS,
  PENDING_DISEASE_KEYS,
  UNITS,
  prodSafeError,
} from '../theme';

// 라벨 — 시나리오 복합표기 ("당뇨병성 신장질환" 등)
const riskLabels = {
  kidney:   `\uB2F9\uB1E8\uBCD1\uC131 ${DISEASE_LABELS.kidney}`,
  cardio:   `${DISEASE_LABELS.cardio} \uC9C8\uD658`,
  cerebro:  `${DISEASE_LABELS.cerebro} \uC9C8\uD658`,
  dementia: DISEASE_LABELS.dementia,
  retina:   DISEASE_LABELS.retina,
  neuro:    DISEASE_LABELS.neuro,
};

// 백엔드 complications 는 v2.0 이후 { level, score } 객체. 과거 문자열 폼도 지원.
function normalizeComplication(v) {
  if (v == null) return { level: null, score: null };
  if (typeof v === 'string') {
    // 구 포맷: 문자열 level 만 — score 는 추정 불가 → null (바는 레벨 기반 fallback)
    return { level: v === '\uC900\uBE44 \uC911' ? null : v, score: null, pending: v === '\uC900\uBE44 \uC911' };
  }
  const isPending = v.level === '\uC900\uBE44 \uC911' || v.score == null;
  return { level: isPending ? null : v.level, score: v.score, pending: isPending };
}

// 전조증상 질환별 라벨 (간결한 카드 헤더용)
const SYMPTOM_DISEASE_LABEL = {
  retina: '망막병증',
  kidney: '신장질환',
  cardio: '심혈관 질환',
};

// 전조증상 등급 배지 스타일
const SYMPTOM_LEVEL_STYLE = {
  HIGH:   { label: 'HIGH',   bg: 'bg-red-100',    text: 'text-red-700',    bullet: 'text-red-500',    rank: 3 },
  MEDIUM: { label: 'MEDIUM', bg: 'bg-amber-100',  text: 'text-amber-700',  bullet: 'text-amber-500',  rank: 2 },
  LOW:    { label: 'LOW',    bg: 'bg-emerald-100',text: 'text-emerald-700',bullet: 'text-emerald-500',rank: 1 },
};

function SymptomGroup({ disease, items }) {
  const label = SYMPTOM_DISEASE_LABEL[disease] || disease;
  return (
    <div className="mb-2 last:mb-0">
      <p className="text-[11px] font-semibold text-gray-700 mb-1">{label}</p>
      <ul className="space-y-1">
        {items.map((s, i) => {
          const style = SYMPTOM_LEVEL_STYLE[s.level] || SYMPTOM_LEVEL_STYLE.LOW;
          return (
            <li key={i} className="text-xs text-gray-600 flex items-center gap-1.5">
              <span aria-hidden="true" className={`${style.bullet} text-[10px] leading-none`}>●</span>
              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider ${style.bg} ${style.text}`}>
                {style.label}
              </span>
              <span>{s.text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function NeglectSymptoms({ neglect }) {
  // 신구 포맷 모두 지원: symptoms_by_disease (객체) → 우선, symptoms (배열) → fallback
  const grouped = neglect?.symptoms_by_disease;
  const hasGrouped = grouped && typeof grouped === 'object' && Object.keys(grouped).length > 0;

  if (hasGrouped) {
    // 표시 순서: 망막 → 신장 → 심혈관 (백엔드 SYMPTOM_BANK 순서 유지)
    const order = ['retina', 'kidney', 'cardio'];
    const keys = order.filter((k) => Array.isArray(grouped[k]) && grouped[k].length > 0);
    if (keys.length === 0) {
      return <p className="text-[11px] text-gray-400 italic">{'\uC9C0\uAE08 \uB2E8\uACC4\uC5D0\uC120 \uD2B9\uBCC4\uD55C \uC804\uC870\uC99D\uC0C1\uC774 \uC608\uC0C1\uB418\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.'}</p>;
    }
    return (
      <div>
        {keys.map((k) => (
          <SymptomGroup key={k} disease={k} items={grouped[k]} />
        ))}
      </div>
    );
  }

  // 구 포맷 (flat string list)
  const flat = Array.isArray(neglect?.symptoms) ? neglect.symptoms : [];
  if (flat.length === 0) return null;
  return (
    <ul className="space-y-1">
      {flat.map((s, i) => (
        <li key={i} className="text-xs text-gray-600 flex gap-1.5">
          <span className="text-red-400" aria-hidden="true">•</span>{s}
        </li>
      ))}
    </ul>
  );
}

function SliderWithBaseline({ id, label, tagline, unit, min, max, step, value, baseline, onChange, disabled }) {
  const baselinePct = ((baseline - min) / (max - min)) * 100;
  const delta = value - baseline;
  const deltaSign = delta > 0 ? '+' : '';
  const deltaColor = Math.abs(delta) < 0.05 ? 'text-gray-400' : delta > 0 ? 'text-orange-500' : 'text-emerald-600';
  const valueText = `${value.toFixed(1)} ${unit} (\uAE30\uC900 ${baseline.toFixed(1)} ${unit} \ub300\ube44 ${Math.abs(delta) < 0.05 ? '\ubcc0\ud654 \uc5c6\uc74c' : `${deltaSign}${delta.toFixed(1)}`})`;
  return (
    <div className="mb-6">
      <div className="flex justify-between items-baseline mb-2">
        <label htmlFor={id} className="text-sm font-medium text-gray-700">
          {label}
          {tagline && <span className="text-[10px] text-accent font-semibold ml-1.5">{tagline}</span>}
        </label>
        <div className="flex items-baseline gap-2">
          <span className={`text-[10px] font-medium ${deltaColor}`}>
            {Math.abs(delta) < 0.05 ? '\uAE30\uC900' : `${deltaSign}${delta.toFixed(1)}`}
          </span>
          <span className="text-lg font-bold text-accent tabular-nums">
            {value.toFixed(1)} <span className="text-xs text-gray-400 font-normal">{unit}</span>
          </span>
        </div>
      </div>
      <div className="relative">
        <input
          id={id}
          type="range"
          min={min} max={max} step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          disabled={disabled}
          aria-valuetext={valueText}
          aria-label={label}
          className="w-full accent-range disabled:opacity-50"
        />
        {/* Baseline tick marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2 pointer-events-none"
          style={{ left: `${baselinePct}%` }}
          title={`\uD658\uC790 \uAE30\uC900\uAC12: ${baseline.toFixed(1)} ${unit}`}
          aria-hidden="true"
        >
          <div className="w-px h-4 bg-gray-400/70 -translate-x-1/2" />
        </div>
      </div>
      <div className="flex justify-between text-[10px] text-gray-400 mt-1.5">
        <span>{min}</span>
        <span className="text-gray-500">
          ▎{'\uD658\uC790 \uAE30\uC900'} {baseline.toFixed(1)} {unit}
        </span>
        <span>{max}</span>
      </div>
    </div>
  );
}

function RiskRow({ label, level, score, pending }) {
  const effectiveLevel = pending ? RISK_LEVELS.NOT_READY : (level || RISK_LEVELS.PENDING);
  const color = riskColorFor(effectiveLevel);
  const isHigh = effectiveLevel === RISK_LEVELS.HIGH;
  // 점수가 있으면 실 점수를 %로, 없으면 레벨별 대표값 (fallback, 시각 목적)
  const levelFallbackPct = isHigh ? 80 : effectiveLevel === RISK_LEVELS.MID ? 45 : effectiveLevel === RISK_LEVELS.LOW ? 18 : 0;
  const pct = pending ? 0 : (typeof score === 'number' ? Math.max(0, Math.min(100, score)) : levelFallbackPct);

  return (
    <div className={pending ? 'opacity-60' : ''}>
      <div className="flex justify-between items-center mb-1">
        <span className={`text-xs flex items-center gap-1.5 ${
          pending ? 'text-gray-400 font-medium italic'
          : isHigh ? 'text-red-600 font-bold'
          : effectiveLevel === RISK_LEVELS.MID ? 'text-amber-700 font-semibold'
          : 'text-gray-600 font-medium'
        }`}>
          {isHigh && (
            <span className="relative flex w-2 h-2" aria-hidden="true">
              <span className="absolute inset-0 rounded-full bg-red-500 opacity-60 animate-ping" />
              <span className="relative rounded-full w-2 h-2 bg-red-500" />
            </span>
          )}
          <span aria-hidden="true" className="text-[10px] leading-none">{color.icon}</span>
          {label}
        </span>
        <span className={`text-xs font-bold flex items-baseline gap-1 ${color.textSoft}`}>
          {pending ? '\uC900\uBE44 \uC911' : effectiveLevel}
          {!pending && typeof score === 'number' && (
            <span className="text-[10px] text-gray-400 font-normal tabular-nums">
              {Math.round(score)}
            </span>
          )}
        </span>
      </div>
      <div
        className={`w-full rounded-full h-1.5 ${pending ? 'bg-gray-100' : isHigh ? 'bg-red-50' : 'bg-gray-100'}`}
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} ${color.ariaLabel}`}
      >
        {!pending && (
          <div
            className={`h-1.5 rounded-full transition-all duration-500 ${color.bar}`}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  );
}

export default function RiskAnalysis() {
  const { patientId } = useParams();
  const { count, loading: countLoading } = usePatientCount();
  const [patient, setPatient] = useState(null);
  const [patientError, setPatientError] = useState(null);
  // 슬라이더 baseline: 환자 실제 값 로드 후 세팅. 로드 전 null 유지.
  const [cpeptide, setCpeptide] = useState(null);
  const [hba1c, setHba1c]       = useState(null);
  const [original, setOriginal] = useState(null);
  const [scenario, setScenario] = useState(null);
  const [scenarioError, setScenarioError] = useState(null);
  const [loading, setLoading] = useState(false);

  const debouncedCpep  = useDebounce(cpeptide, 300);
  const debouncedHba1c = useDebounce(hba1c, 300);

  // 진행 중인 scenario 요청 abort (슬라이더 빠르게 움직일 때 stale 응답 방지)
  const abortRef = useRef(null);

  // Initial patient load
  useEffect(() => {
    if (countLoading || count === 0) return;
    (async () => {
      try {
        const res = await api.get(`/patients/${patientId}`);
        const d = res.data.data;
        const p = d.patient || d;
        setPatient(p);
        setPatientError(null);
        // 환자 실 값이 없으면 null → baseline 미정. 시뮬레이션 버튼은 비활성.
        const cp = p.c_peptide != null ? Number(p.c_peptide) : null;
        const hb = p.hba1c     != null ? Number(p.hba1c)     : null;
        setCpeptide(cp);
        setHba1c(hb);
        setOriginal(cp != null && hb != null ? { cpeptide: cp, hba1c: hb } : null);
      } catch (e) {
        prodSafeError('RiskAnalysis.loadPatient')(e);
        setPatientError(e.response?.data?.detail || e.message);
      }
    })();
  }, [patientId, count, countLoading]);

  // Simulate on slider change (debounced)
  const fetchScenario = useCallback(async () => {
    if (debouncedCpep == null || debouncedHba1c == null) return;
    // 이전 요청 abort
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setScenarioError(null);
    try {
      const res = await api.post('/scenario/simulate', {
        patient_id: parseInt(patientId, 10),
        c_peptide: debouncedCpep,
        hba1c: debouncedHba1c,
      }, { signal: controller.signal });
      setScenario(res.data.data);
    } catch (e) {
      if (e.name === 'CanceledError' || e.name === 'AbortError') return;
      prodSafeError('RiskAnalysis.scenario')(e);
      setScenarioError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [patientId, debouncedCpep, debouncedHba1c]);

  useEffect(() => {
    if (patient && original) fetchScenario();
  }, [patient, original, fetchScenario]);

  // cleanup abort on unmount
  useEffect(() => () => { if (abortRef.current) abortRef.current.abort(); }, []);

  const reset = () => {
    if (!original) return;
    setCpeptide(original.cpeptide);
    setHba1c(original.hba1c);
  };

  if (countLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
      </div>
    );
  }
  if (count === 0) {
    return <EmptyState title={'\uB4F1\uB85D\uB41C \uD658\uC790\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4'} message={'CSV \uD30C\uC77C\uC744 \uC5C5\uB85C\uB4DC\uD574 \uD658\uC790 \uB370\uC774\uD130\uB97C \uB4F1\uB85D\uD558\uBA74 \uC2DC\uB098\uB9AC\uC624 \uBD84\uC11D\uC744 \uC0AC\uC6A9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.'} />;
  }
  if (patientError) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="bg-white rounded-xl p-8 border border-red-200 text-center max-w-md">
          <AlertCircle size={32} className="text-red-500 mx-auto mb-3" />
          <p className="text-sm font-bold text-gray-800 mb-1">{'\uD658\uC790 \uC815\uBCF4\uB97C \uBD88\uB7EC\uC62C \uC218 \uC5C6\uC2B5\uB2C8\uB2E4'}</p>
          <p className="text-xs text-gray-500 mb-4">{patientError}</p>
          <Link to="/patients" className="text-xs text-accent font-semibold hover:underline">{'\uD658\uC790 \uBAA9\uB85D\uC73C\uB85C \uB3CC\uC544\uAC00\uAE30'}</Link>
        </div>
      </div>
    );
  }
  if (!patient) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
      </div>
    );
  }
  // 환자 값 미입력 → 시뮬레이션 불가 (baseline 없으므로)
  if (!original) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center max-w-md">
          <AlertCircle size={28} className="text-amber-500 mx-auto mb-3" />
          <p className="text-sm font-bold text-gray-800 mb-1">
            {'C-peptide \ub610\ub294 HbA1c \uAC12\uC774 \uC785\ub825\ub418\uC5B4 \uC788\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4'}
          </p>
          <p className="text-xs text-gray-500 mb-4">
            {'\uC2DC\uB098\ub9AC\uC624 \uBD84\uC11D\uC740 \ud658\uc790 \uAE30\uC900\uAC12\uC774 \uC788\uC5B4\uC57C \uC2DC\uC791\ud560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.'}
          </p>
          <Link to={`/patients/${patientId}`} className="text-xs text-accent font-semibold hover:underline">
            {'\ud658\uc790 \uc0c1\uc138\ub85c \uc774\ub3d9 \ubc0f \uc218\uc815'}
          </Link>
        </div>
      </div>
    );
  }

  // complications 정규화 (문자열/객체 폼 모두 지원)
  const neglectComps  = scenario?.neglect?.complications  || {};
  const intensiveComps = scenario?.intensive?.complications || {};
  const graduationComps = scenario?.graduation?.complications || {};

  // v2.1 — 저위험 환자 + 슬라이더 미변경 시 "치료 방치" 톤 완화
  const isMaintain = scenario?.neglect?.label_mode === 'maintain';
  const neglectTitle = isMaintain ? '현재 수치 유지 시 (1~2년 후)' : '치료 방치 시';
  const neglectSubLabel = isMaintain ? '안정 단계 유지 가능' : '초기 합병증 위험';
  const neglectIconBg = isMaintain ? 'bg-amber-50' : 'bg-orange-100';
  const neglectIconColor = isMaintain ? 'text-amber-500' : 'text-orange-500';
  const neglectNumberColor = isMaintain ? 'text-amber-600' : 'text-red-500';
  const neglectStatBg = isMaintain ? 'bg-amber-50/60' : 'bg-red-50';

  return (
    <div className="space-y-6 fade-in w-full">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{'\uC2DC\uB098\uB9AC\uC624 \uAE30\uBC18 \uD569\uBCD1\uC99D \uBD84\uC11D'}</h1>
          <p className="text-[11px] text-gray-400 uppercase tracking-[0.18em] mt-1.5">RISK ANALYSIS & SCENARIO PLANNING</p>
        </div>
        {patient && (
          <Link
            to={`/case-comparison/${patientId}`}
            className="hidden sm:inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:opacity-80 transition-opacity"
          >
            {'\uC720\uC0AC \uC0AC\uB840 \uBE44\uAD50 \uBCF4\uAE30'} <ArrowRight size={12} />
          </Link>
        )}
      </div>

      {/* Top row: Simulator + Radar */}
      <div className="grid grid-cols-2 gap-5">
        {/* Simulator */}
        <div className="bg-white rounded-xl p-6 border border-gray-100 shadow-sm">
          <div className="flex justify-between items-center mb-5">
            <h3 className="text-sm font-bold text-gray-800">{'\uAC74\uAC15 \uC9C0\uD45C \uC2DC\uBBAC\uB808\uC774\uC158'}</h3>
            <button
              onClick={reset}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-accent transition-colors"
            >
              <RotateCcw size={12} aria-hidden="true" /> {'\uCD08\uAE30\uD654'}
            </button>
          </div>

          {/* C-peptide slider */}
          <SliderWithBaseline
            id="sim-cpeptide"
            label="C-peptide"
            tagline={'\uD575\uC2EC \uC9C0\uD45C'}
            unit={UNITS.cpeptide}
            min={0.5}
            max={5.0}
            step={0.1}
            value={cpeptide}
            baseline={original.cpeptide}
            onChange={setCpeptide}
            disabled={loading}
          />

          {/* HbA1c slider */}
          <SliderWithBaseline
            id="sim-hba1c"
            label={'\uB2F9\uD654\uD608\uC0C9\uC18C (HbA1c)'}
            unit={UNITS.percent}
            min={5.0}
            max={15.0}
            step={0.1}
            value={hba1c}
            baseline={original.hba1c}
            onChange={setHba1c}
            disabled={loading}
          />

          {/* Tip */}
          <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 flex gap-2">
            <Lightbulb size={16} className="text-blue-500 shrink-0 mt-0.5" aria-hidden="true" />
            <p className="text-xs text-blue-900">
              {'C-peptide \uC218\uCE58\uB97C 1%\uB9CC \uAC1C\uC120\uD574\uB3C4 \uD569\uBCD1\uC99D \uBC1C\uBCD1 \uC704\uD5D8\uC774 \uC720\uC758\uBBF8\uD558\uAC8C \uAC10\uC18C\uD558\uB294 \uD6A8\uACFC\uAC00 \uC2DC\uBBAC\uB808\uC774\uC158 \uB418\uC5C8\uC2B5\uB2C8\uB2E4.'}
            </p>
          </div>
        </div>

        {/* Radar chart */}
        <div className="bg-white rounded-xl p-6 border border-gray-100 shadow-sm relative">
          <h3 className="text-sm font-bold text-gray-800 mb-4">{'\uD569\uBCD1\uC99D \uB9AC\uC2A4\uD06C \uD504\uB85C\uD544'}</h3>
          {loading && (
            <div
              className="absolute top-6 right-6 w-4 h-4 animate-spin rounded-full border-2 border-accent border-t-transparent"
              aria-label="\uC2DC\uBBAC\uB808\uC774\uC158 \uACC4\uC0B0 \uC911"
              role="status"
            />
          )}
          <RadarChart data={scenario?.radar || {}} />
        </div>
      </div>

      {/* Scenario loading / error states */}
      {!scenario && !scenarioError && (
        <div className="bg-white rounded-xl p-10 border border-dashed border-indigo-200 text-center">
          <Loader2 size={32} className="text-accent animate-spin mx-auto mb-3" aria-hidden="true" />
          <p className="text-sm font-semibold text-gray-700">{'\uC2DC\uB098\uB9AC\uC624\uB97C \uACC4\uC0B0\uD558\uACE0 \uC788\uC2B5\uB2C8\uB2E4...'}</p>
          <p className="text-xs text-gray-400 mt-1">{'\uCE58\uB8CC \uBC29\uCE58 / \uC9D1\uC911\uAD00\uB9AC \uBE44\uAD50 \uBD84\uC11D \uC900\uBE44 \uC911'}</p>
        </div>
      )}
      {scenarioError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <AlertCircle size={24} className="text-red-500 mx-auto mb-2" aria-hidden="true" />
          <p className="text-sm font-semibold text-red-700">{'\uC2DC\uB098\uB9AC\uC624 \uC2DC\uBBAC\uB808\uC774\uC158 \uC2E4\uD328'}</p>
          <p className="text-xs text-red-600 mt-1">{scenarioError}</p>
          <button
            onClick={fetchScenario}
            className="mt-3 inline-flex items-center gap-1 text-xs text-red-700 font-semibold hover:underline"
          >
            <RotateCcw size={12} aria-hidden="true" /> {'\ub2e4\uc2dc \uc2dc\ub3c4'}
          </button>
        </div>
      )}

      {/* Scenario comparison */}
      {scenario && (
        <div className="grid grid-cols-3 gap-5">
          {/* NEGLECT */}
          <div className="bg-white rounded-xl p-6 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <div className={`w-10 h-10 rounded-full ${neglectIconBg} flex items-center justify-center`}>
                <AlertCircle size={20} className={neglectIconColor} aria-hidden="true" />
              </div>
              <h3 className="text-base font-bold text-gray-800">{neglectTitle}</h3>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className={neglectStatBg + " rounded-lg p-3"}>
                <p className="text-[10px] text-gray-500 mb-1">{'\uC608\uC0C1 \uAC74\uAC15\uC218\uBA85'}</p>
                <p className={"text-2xl font-bold " + neglectNumberColor}>{scenario.neglect.life_expectancy}<span className="text-sm">{'\uC138'}</span></p>
                <p className={"text-[10px] mt-1 " + neglectNumberColor}>{neglectSubLabel}</p>
              </div>
              <div className={neglectStatBg + " rounded-lg p-3"}>
                <p className="text-[10px] text-gray-500 mb-1">{'\uC608\uC0C1 \uC758\uB8CC\uBE44'}</p>
                <p className={"text-2xl font-bold " + neglectNumberColor}>{scenario.neglect.annual_cost_man.toLocaleString()}<span className="text-sm">{'\uB9CC'}</span></p>
                <p className={"text-[10px] mt-1 " + neglectNumberColor}>+{scenario.neglect.cost_increase_pct}% {'\uC99D\uAC00'}</p>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <p className="text-xs font-semibold text-gray-700 mb-2">{'\uC9C0\uD45C \uC545\uD654 \uC608\uCE21'}</p>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500">{'\uB2F9\uB1E8\uC57D \uAC1C\uC218'}</span>
                <span className="font-semibold">{scenario.neglect.drug_count_before}{'\uAC1C'} {'\u2192'} {scenario.neglect.drug_count_after}{'\uAC1C'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">{'\uC778\uC290\uB9B0 \uB9DE\uC744 \uD655\uB960'}</span>
                <span className="font-semibold text-red-600">{scenario.neglect.insulin_probability}%</span>
              </div>
            </div>

            <div className="space-y-2 mb-4">
              {Object.entries(neglectComps).map(([k, raw]) => {
                const { level, score, pending } = normalizeComplication(raw);
                const foldData = scenario?.fold_change_by_disease?.[k];
                return (
                  <div key={k}>
                    <RiskRow label={riskLabels[k] || k} level={level} score={score} pending={pending} />
                    {foldData?.fold != null && (
                      <p className="text-[10px] text-gray-500 ml-4 -mt-0.5">
                        같은 나이대 대비 {Number(foldData.fold).toFixed(2)}배
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-700 mb-2">체감되는 전조 증상</p>
              <NeglectSymptoms neglect={scenario.neglect} />
            </div>
          </div>

          {/* INTENSIVE */}
          <div className="bg-white rounded-xl p-6 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
                <Zap size={20} className="text-green-500" aria-hidden="true" />
              </div>
              <h3 className="text-base font-bold text-gray-800">{'\uC9D1\uC911\uAD00\uB9AC \uC2DC (6\uAC1C\uC6D4 \uD6C4)'}</h3>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="bg-green-50 rounded-lg p-3">
                <p className="text-[10px] text-gray-500 mb-1">{'\uC608\uC0C1 \uAC74\uAC15\uC218\uBA85'}</p>
                <p className="text-2xl font-bold text-green-600">{scenario.intensive.life_expectancy}<span className="text-sm">{'\uC138'}</span></p>
                <p className="text-[10px] text-green-600 mt-1">{'\uAC74\uAC15\uC218\uBA85 \uC5F0\uC7A5 \uC608\uCE21'}</p>
              </div>
              <div className="bg-green-50 rounded-lg p-3">
                <p className="text-[10px] text-gray-500 mb-1">{'\uC608\uC0C1 \uC758\uB8CC\uBE44'}</p>
                <p className="text-2xl font-bold text-green-600">{scenario.intensive.annual_cost_man}<span className="text-sm">{'\uB9CC'}</span></p>
                <p className="text-[10px] text-green-600 mt-1">-{scenario.intensive.cost_decrease_pct}% {'\uAC10\uC18C'}</p>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <p className="text-xs font-semibold text-gray-700 mb-2">{'\uC9C0\uD45C \uAC1C\uC120 \uC608\uCE21'}</p>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500">{'\uB2F9\uD654\uD608\uC0C9\uC18C'}</span>
                <span className="font-semibold text-green-600">{scenario.intensive.hba1c_before}% {'\u2192'} {scenario.intensive.hba1c_after}%</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">C-peptide</span>
                <span className="font-semibold text-green-600">
                  {scenario.intensive.cpeptide_before} {'\u2192'} {scenario.intensive.cpeptide_after} {UNITS.cpeptide}
                  <span className="text-[10px] text-gray-500 font-normal ml-1">{'(\uc815\uc0c1\ubc94\uc704 1.0\u20133.5 \uc218\ub834)'}</span>
                </span>
              </div>
            </div>

            <div className="space-y-2 mb-4">
              {Object.entries(intensiveComps).map(([k, raw]) => {
                const { level, score, pending } = normalizeComplication(raw);
                return (
                  <RiskRow key={k} label={riskLabels[k] || k} level={level} score={score} pending={pending} />
                );
              })}
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-700 mb-2">{'\uD68C\uBCF5\uB418\uB294 \uC804\uC870\uC99D\uC0C1'}</p>
              {(() => {
                const resolved = scenario.intensive.symptoms_resolved_by_disease;
                const orderArr = ['retina', 'kidney', 'cardio'];
                const keys = resolved ? orderArr.filter((k) => resolved[k]) : [];
                if (keys.length === 0) {
                  return (
                    <ul className="space-y-1">
                      {scenario.intensive.improvements.map((s, i) => (
                        <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                          <span className="text-green-500" aria-hidden="true">{'\u2022'}</span>{s}
                        </li>
                      ))}
                    </ul>
                  );
                }
                return (
                  <ul className="space-y-1.5">
                    {keys.map((k) => (
                      <li key={k} className="text-xs text-gray-700 flex items-start gap-1.5">
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider bg-emerald-100 text-emerald-700 shrink-0 mt-0.5">
                          {SYMPTOM_DISEASE_LABEL[k] || k}
                        </span>
                        <span>{resolved[k]}</span>
                      </li>
                    ))}
                  </ul>
                );
              })()}
            </div>
          </div>

          {/* GRADUATION (v2.1.5 - fixed standard values) */}
          <div className="bg-white rounded-xl p-6 border border-purple-100 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
                <GraduationCap size={20} className="text-purple-600" aria-hidden="true" />
              </div>
              <h3 className="text-base font-bold text-gray-800">{'\uC878\uC5C5 \uC2DC (\uD45C\uC900\uAC12)'}</h3>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="bg-purple-50 rounded-lg p-3">
                <p className="text-[10px] text-gray-500 mb-1">{'\uC608\uC0C1 \uAC74\uAC15\uC218\uBA85'}</p>
                <p className="text-2xl font-bold text-purple-600">
                  {scenario.graduation.life_expectancy}<span className="text-sm">{'\uC138'}</span>
                </p>
                {scenario.graduation.delta_vs_neglect && (
                  <p className="text-[10px] text-purple-600 mt-1 font-semibold">
                    방치 대비 +{scenario.graduation.delta_vs_neglect.life_expectancy}년 증가
                  </p>
                )}
              </div>
              <div className="bg-purple-50 rounded-lg p-3">
                <p className="text-[10px] text-gray-500 mb-1">{'\uC608\uC0C1 \uC758\uB8CC\uBE44'}</p>
                <p className="text-2xl font-bold text-purple-600">
                  {scenario.graduation.annual_cost_man}<span className="text-sm">{'\uB9CC'}</span>
                </p>
                {scenario.graduation.delta_vs_neglect && (
                  <p className="text-[10px] text-purple-600 mt-1 font-semibold">
                    -{scenario.graduation.delta_vs_neglect.annual_cost_decrease}만원 감소
                  </p>
                )}
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <p className="text-xs font-semibold text-gray-700 mb-2">{'\uC878\uC5C5 \uAE30\uC900\uAC12'}</p>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500">HbA1c / C-peptide</span>
                <span className="font-semibold text-purple-700">
                  {scenario.graduation.standard_values.hba1c}% / {scenario.graduation.standard_values.c_peptide} ng/mL
                </span>
              </div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500">{'\uACF5\uBCF5\uD608\uB2F9 / BMI'}</span>
                <span className="font-semibold text-purple-700">
                  {scenario.graduation.standard_values.fbg} mg/dL / {scenario.graduation.standard_values.bmi}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">{'\uD608\uC555'}</span>
                <span className="font-semibold text-purple-700">
                  {scenario.graduation.standard_values.sbp}/{scenario.graduation.standard_values.dbp} mmHg
                </span>
              </div>
            </div>

            <div className="space-y-2 mb-4">
              {Object.entries(graduationComps).map(([k, raw]) => {
                const { level, score, pending } = normalizeComplication(raw);
                const delta = scenario.graduation.delta_vs_neglect?.complications?.[k];
                return (
                  <div key={k}>
                    <RiskRow label={riskLabels[k] || k} level={level} score={score} pending={pending} />
                    {delta != null && delta > 0 && (
                      <p className="text-[10px] text-purple-600 ml-4 -mt-0.5 font-semibold">
                        방치 대비 {delta.toFixed(1)}점 감소
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <p className="text-[11px] text-gray-400 italic">
              {'\uC2AC\uB77C\uC774\uB354 \uC601\uD5A5 \uC5C6\uB294 \uD45C\uC900\uAC12 \uAE30\uC900'}
            </p>
          </div>
        </div>
      )}

      {/* Clinical note */}
      {scenario?.clinical_note && (
        <p className="text-[11px] text-gray-400 text-center -mt-2">{scenario.clinical_note}</p>
      )}

      {/* Recommended program */}
      {scenario?.recommended_program && (
        <div className="gradient-accent rounded-xl p-6 text-white flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs uppercase tracking-wider opacity-80 mb-1">{'\uCD5C\uC801 \uAD8C\uC7A5 \uD504\uB85C\uADF8\uB7A8'}</p>
            <h3 className="text-xl font-bold mb-1">{scenario.recommended_program.name}</h3>
            <p className="text-sm opacity-90">{scenario.recommended_program.description}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link
              to={`/case-comparison/${patientId}`}
              className="flex items-center gap-1.5 bg-white/15 hover:bg-white/25 text-white px-4 py-2.5 rounded-lg text-sm font-semibold transition-colors"
            >
              {'\uC720\uC0AC \uC0AC\uB840 \uBCF4\uAE30'}
            </Link>
            <button className="flex items-center gap-2 bg-white text-accent px-5 py-2.5 rounded-lg text-sm font-semibold hover:bg-white/90 transition-colors">
              {'\uD504\uB85C\uADF8\uB7A8 \uC2E0\uCCAD \uC548\uB0B4'} <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
