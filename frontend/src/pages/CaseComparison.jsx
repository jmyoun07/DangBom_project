import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Check, Database, Filter, Target, TrendingUp, Loader2, Sparkles, Search, Cpu } from 'lucide-react';
import api from '../api/client';
import usePatientCount from '../hooks/usePatientCount';
import EmptyState from '../components/EmptyState';
import { prodSafeError } from '../theme';

// prefers-reduced-motion 환경 감지 (고스트 애니메이션 비활성화용)
const prefersReducedMotion = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// Step durations bumped a bit so the search feels deliberate (not "too fast = fake")
const STEPS = [
  { num: '01', title: '\uB370\uC774\uD130 \uC218\uC9D1 \uBC0F \uC815\uC81C', subtitle: '\uD658\uC790 \uAE30\uBCF8 \uC815\uBCF4 \uBD84\uC11D', icon: Database, duration: 1100 },
  { num: '02', title: '\uD575\uC2EC \uD2B9\uC9D5 \uCD94\uCD9C', subtitle: 'ML \uBCC0\uC218\uC5D0\uC11C \uD2B9\uC9D5 \uBCA1\uD130 \uC0DD\uC131', icon: Filter, duration: 1300 },
  { num: '03', title: '\uC720\uC0AC\uB3C4 \uC54C\uACE0\uB9AC\uC998 \uAC00\uB3D9', subtitle: 'k-NN \uAE30\uBC18 \uCD5C\uADFC\uC811 \uC0AC\uB840 \uAC80\uC0C9', icon: Target, duration: 1700 },
  { num: '04', title: '\uC0C1\uC704 3\uAC1C \uC0AC\uB840 \uD655\uC815', subtitle: '\uAC80\uC99D \uBC0F \uC21C\uC704\uD654', icon: TrendingUp, duration: 1100 },
];

const COMP_ORDER = ['kidney', 'cardio', 'cerebro', 'dementia', 'retina', 'neuro'];

// ────────────────────────────────────────────────────────────────
// Final case card (settles into place via .card-settle)
// ────────────────────────────────────────────────────────────────
function CaseCard({ c, index }) {
  const hasHbA1c = c.hba1c_before != null && c.hba1c_after != null;
  const hasCpep = c.c_peptide_before != null && c.c_peptide_after != null;
  const hasMonths = c.treatment_months != null && c.treatment_months > 0;
  const hasDxYears = c.dx_years != null;
  const sexLabel = c.sex === 'M' ? '남' : c.sex === 'F' ? '여' : '-';
  // 이력 없을 때 단일 시점 fallback (현재 환자 값)
  const hba1cCurrent = c.hba1c_current;
  const cpepCurrent = c.c_peptide_current;
  return (
    <div
      className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm card-settle"
      style={{ '--settle-delay': `${index * 0.18}s` }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-11 h-11 rounded-full bg-gray-800 flex items-center justify-center text-white font-bold">
          {c.name?.[0] || '?'}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-gray-800">{c.name}</h3>
            <span className="bg-green-100 text-green-700 text-[10px] px-2 py-0.5 rounded-full font-semibold">
              유사도 {c.similarity_pct}%
            </span>
          </div>
          <p className="text-[11px] text-gray-400 mt-0.5">
            {c.age != null ? `${c.age}세` : '나이 미상'} / {sexLabel}
          </p>
        </div>
        <TrendingUp size={14} className="text-green-500" />
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">HbA1c {hasHbA1c ? '변화' : '현재'}</p>
          {hasHbA1c ? (
            <p className="text-xs font-semibold text-gray-700">
              {c.hba1c_before}% {'→'} <span className="text-green-600">{c.hba1c_after}%</span>
            </p>
          ) : hba1cCurrent != null ? (
            <p className="text-xs font-semibold text-gray-700">{hba1cCurrent}%</p>
          ) : (
            <p className="text-xs text-gray-400">정보 없음</p>
          )}
        </div>
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">C-peptide {hasCpep ? '변화' : '현재'}</p>
          {hasCpep ? (
            <p className="text-xs font-semibold text-gray-700">
              {c.c_peptide_before} {'→'} <span className="text-green-600">{c.c_peptide_after}</span>
              <span className="text-[10px] text-gray-400 ml-0.5">{'ng/mL'}</span>
            </p>
          ) : cpepCurrent != null ? (
            <p className="text-xs font-semibold text-gray-700">
              {cpepCurrent} <span className="text-[10px] text-gray-400 ml-0.5">{'ng/mL'}</span>
            </p>
          ) : (
            <p className="text-xs text-gray-400">정보 없음</p>
          )}
        </div>
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">치료 기간</p>
          {hasMonths ? (
            <div className="flex items-center gap-1.5">
              <p className="text-xs font-semibold text-gray-700">{c.treatment_months}개월</p>
              <span className="bg-blue-100 text-blue-700 text-[9px] px-1.5 py-0.5 rounded font-semibold">
                {c.treatment_type}
              </span>
            </div>
          ) : (
            <p className="text-xs text-gray-400">-</p>
          )}
        </div>
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">진단 경과</p>
          <p className="text-xs font-semibold text-gray-700">
            {hasDxYears ? `${c.dx_years}년차` : '-'}
          </p>
        </div>
      </div>

      <hr className="my-4 border-gray-100" />

      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <p className="text-[11px] font-semibold text-gray-700">{'\uD569\uBCD1\uC99D \uC704\uD5D8\uB3C4 \uBCC0\uD654 (\uCD08\uAE30 \uCE21\uC815 \u2192 \uCD5C\uADFC \uCE21\uC815)'}</p>
        </div>
        {(() => {
          const comps = COMP_ORDER.map((k) => c.complications?.[k]).filter(Boolean);
          const hasChange = comps.some((cm) => cm.before_pct !== cm.after_pct);
          if (!hasChange && comps.length > 0) {
            return (
              <p className="text-[10px] text-gray-400 italic mb-2">
                {'측정 이력 1회 — 시간에 따른 변화는 추후 검사 누적 시 표시됩니다.'}
              </p>
            );
          }
          if (hasChange) {
            return (
              <div className="flex gap-3 text-[10px] text-gray-400 mb-2">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" />{'초기'}</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500" />{'최근'}</span>
              </div>
            );
          }
          return null;
        })()}
        <div className="space-y-2">
          {COMP_ORDER.map((key) => {
            const comp = c.complications?.[key];
            if (!comp) return null;
            const same = comp.before_pct === comp.after_pct;
            return (
              <div key={key}>
                <div className="flex justify-between text-[10px] text-gray-600 mb-1">
                  <span>{comp.name}</span>
                  <span className="font-semibold">
                    {same
                      ? `${comp.after_pct}%`
                      : <>{comp.before_pct}% <span className="text-gray-400">{'→'}</span> {comp.after_pct}%</>}
                  </span>
                </div>
                <div className="flex-1 bg-gray-100 rounded-full h-1 overflow-hidden">
                  <div className="h-1 bg-red-400 rounded-full" style={{ width: `${comp.before_pct}%` }} />
                </div>
                {!same && (
                  <div className="flex-1 bg-gray-100 rounded-full h-1 overflow-hidden mt-1">
                    <div className="h-1 bg-blue-500 rounded-full" style={{ width: `${comp.after_pct}%` }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <hr className="my-4 border-gray-100" />

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="bg-green-50 rounded-lg p-2.5 text-center">
          <p className="text-[9px] text-gray-500 mb-0.5">{'\uC758\uB8CC\uBE44 \uC808\uAC10'}</p>
          <p className="text-sm font-bold text-green-600">{'\uC5F0'} {c.cost_saving_annual_man}{'\uB9CC\uC6D0'}</p>
        </div>
        <div className="bg-purple-50 rounded-lg p-2.5 text-center">
          <p className="text-[9px] text-gray-500 mb-0.5">{'\uAE30\uB300 \uAC74\uAC15\uC218\uBA85'}</p>
          <p className="text-sm font-bold text-purple-600">{c.expected_healthy_age}{'\uC138'}</p>
        </div>
      </div>

    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// Stepper (unchanged — kept simple as user requested)
// ────────────────────────────────────────────────────────────────
function Stepper({ activeStep, completed }) {
  const N = STEPS.length;
  // 각 flex-1 셀 너비의 중앙이 원 중심. 4스텝 → 12.5% / 37.5% / 62.5% / 87.5%.
  const startPct = 50 / N; // 12.5
  const endPct = 100 - startPct; // 87.5
  const spanPct = endPct - startPct; // 75
  // 진행률: 첫 원 → activeStep 원. completed면 끝 원까지.
  const filledPct = completed
    ? spanPct
    : (activeStep / (N - 1)) * spanPct;

  return (
    <div className="bg-white rounded-xl p-6 border border-gray-100 shadow-sm">
      <div className="flex items-start justify-between relative">
        {/* 배경 가로선 — 첫 원 중심부터 마지막 원 중심까지 */}
        <div
          className="absolute top-6 h-0.5 bg-gray-200 rounded-full"
          style={{ left: `${startPct}%`, right: `${startPct}%` }}
        />
        {/* 진행 가로선 — 첫 원에서 activeStep 원까지 */}
        <div
          className="absolute top-6 h-0.5 rounded-full transition-all duration-500"
          style={{
            left: `${startPct}%`,
            width: `${filledPct}%`,
            backgroundColor: 'var(--db-accent)',
          }}
        />
        {STEPS.map((step, i) => {
          const Icon = step.icon;
          const isDone = completed || i < activeStep;
          const isActive = !completed && i === activeStep;
          const isPending = !isDone && !isActive;
          return (
            <div key={step.num} className="relative flex flex-col items-center z-10 flex-1">
              <div className="relative">
                <div
                  className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-500 ${
                    isDone
                      ? 'bg-accent text-white shadow-md'
                      : isActive
                      ? 'bg-accent text-white shadow-lg animate-pulse'
                      : 'bg-gray-100 text-gray-400'
                  }`}
                  style={isActive ? { boxShadow: '0 0 0 4px var(--db-accent-ring)' } : undefined}
                >
                  {isActive ? <Loader2 size={18} className="animate-spin" /> : <Icon size={18} />}
                </div>
                {isDone && (
                  <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-green-500 flex items-center justify-center shadow-sm ring-2 ring-white">
                    <Check size={12} className="text-white" />
                  </div>
                )}
              </div>
              <p className={`text-[10px] mt-3 font-medium ${isPending ? 'text-gray-400' : 'text-gray-500'}`}>
                STEP {step.num}
              </p>
              <p className={`text-xs font-semibold mt-0.5 text-center ${isPending ? 'text-gray-400' : 'text-gray-800'}`}>
                {step.title}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5 text-center max-w-[140px] leading-tight">
                {step.subtitle}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// "Searching" canvas — flying ghost cards + orbit rings + scanner
// Goal: convince a non-technical, elderly viewer that the AI is
// genuinely sifting through many records (not just instant magic).
// ────────────────────────────────────────────────────────────────
const GHOST_NAMES = ['김O식', '이O희', '박O철', '정O자', '최O민', '강O수', '윤O경', '조O환', '한O진', '서O은', '문O호', '오O정'];
const GHOST_HUES = ['#fef3c7', '#dbeafe', '#dcfce7', '#fee2e2', '#ede9fe', '#cffafe'];

function makeGhost(i) {
  // Spread cards across all four entry directions; randomize rotation/duration/delay
  const dir = i % 4; // 0=L→R, 1=R→L, 2=T→B, 3=B→T
  const rand = (a, b) => a + Math.random() * (b - a);
  let txFrom, txTo, tyFrom, tyTo;
  if (dir === 0) { txFrom = '-220%'; txTo = '220%'; tyFrom = `${rand(-60, 60)}%`; tyTo = `${rand(-60, 60)}%`; }
  else if (dir === 1) { txFrom = '220%'; txTo = '-220%'; tyFrom = `${rand(-60, 60)}%`; tyTo = `${rand(-60, 60)}%`; }
  else if (dir === 2) { txFrom = `${rand(-80, 80)}%`; txTo = `${rand(-80, 80)}%`; tyFrom = '-220%'; tyTo = '220%'; }
  else { txFrom = `${rand(-80, 80)}%`; txTo = `${rand(-80, 80)}%`; tyFrom = '220%'; tyTo = '-220%'; }
  return {
    id: i,
    txFrom, txTo, tyFrom, tyTo,
    rotFrom: `${rand(-35, -10)}deg`,
    rotTo: `${rand(10, 35)}deg`,
    duration: `${rand(2.6, 4.2).toFixed(2)}s`,
    delay: `${(i * 0.22 + Math.random() * 0.2).toFixed(2)}s`,
    width: Math.floor(rand(150, 200)),
    name: GHOST_NAMES[i % GHOST_NAMES.length],
    sex: i % 2 === 0 ? 'M' : 'F',
    age: Math.floor(rand(48, 76)),
    sim: Math.floor(rand(72, 96)),
    accent: GHOST_HUES[i % GHOST_HUES.length],
  };
}

function GhostCard({ g }) {
  return (
    <div
      className="absolute card-fly bg-white rounded-lg border border-gray-100 shadow-md px-3 py-2.5"
      style={{
        '--tx-from': g.txFrom,
        '--tx-to': g.txTo,
        '--ty-from': g.tyFrom,
        '--ty-to': g.tyTo,
        '--rot-from': g.rotFrom,
        '--rot-to': g.rotTo,
        '--fly-dur': g.duration,
        '--fly-delay': g.delay,
        width: `${g.width}px`,
        left: '50%',
        top: '50%',
        marginLeft: `-${g.width / 2}px`,
        marginTop: '-32px',
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-gray-700 shrink-0"
          style={{ backgroundColor: g.accent }}
        >
          {g.name[0]}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold text-gray-800 truncate">{g.name}</p>
          <p className="text-[8px] text-gray-400">{g.age}{'\uC138 / '}{g.sex === 'M' ? '\uB0A8' : '\uC5EC'}</p>
        </div>
        <span className="text-[8px] font-bold text-emerald-600 bg-emerald-50 rounded px-1 py-0.5">
          {g.sim}%
        </span>
      </div>
      <div className="space-y-1">
        <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-1 bg-gray-300 rounded-full" style={{ width: `${g.sim}%` }} />
        </div>
        <div className="h-1 bg-gray-50 rounded w-3/4" />
      </div>
    </div>
  );
}

function SearchingDeck({ activeStep, recordsScanned, totalCount }) {
  // 접근성: prefers-reduced-motion 이면 고스트 8개로 축소. 그 외 14개.
  const ghostCount = prefersReducedMotion ? 8 : 14;
  const ghosts = useMemo(() => Array.from({ length: ghostCount }, (_, i) => makeGhost(i)), [ghostCount]);
  const step = STEPS[activeStep] || STEPS[0];
  const StepIcon = step.icon;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden relative">
      {/* Scanner sweep */}
      <div className="pointer-events-none absolute inset-x-0 top-0 bottom-0 overflow-hidden">
        <div
          className="scanner-bar absolute left-0 right-0 h-32"
          style={{
            background: 'linear-gradient(to bottom, transparent, var(--db-accent-soft) 40%, var(--db-accent-soft) 60%, transparent)',
            opacity: 0.45,
          }}
        />
      </div>

      <div className="relative" style={{ height: 360 }}>
        {/* Ghost cards flying past */}
        {ghosts.map((g) => <GhostCard key={g.id} g={g} />)}

        {/* Center orbital scanner */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="relative w-48 h-48">
            {/* outer dashed ring */}
            <div
              className="absolute inset-0 rounded-full border-2 border-dashed orbit-slow"
              style={{ borderColor: 'var(--db-accent-ring)' }}
            />
            {/* inner ring */}
            <div
              className="absolute inset-6 rounded-full border-2 border-dashed orbit-fast"
              style={{ borderColor: 'var(--db-accent-ring)' }}
            />
            {/* halo pulses */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div
                className="absolute w-20 h-20 rounded-full halo-pulse"
                style={{ backgroundColor: 'var(--db-accent-ring)' }}
              />
              <div
                className="absolute w-20 h-20 rounded-full halo-pulse"
                style={{ backgroundColor: 'var(--db-accent-ring)', animationDelay: '0.7s' }}
              />
            </div>
            {/* core */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-20 h-20 rounded-full gradient-accent flex items-center justify-center text-white shadow-2xl">
                <Search size={32} className="animate-pulse" />
              </div>
            </div>
            {/* rotating satellite icons */}
            <div className="absolute inset-0 orbit-slow">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center">
                <Cpu size={14} className="text-accent" />
              </div>
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center">
                <Database size={14} className="text-accent" />
              </div>
              <div className="absolute top-1/2 left-0 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center">
                <Filter size={14} className="text-accent" />
              </div>
              <div className="absolute top-1/2 right-0 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center">
                <Sparkles size={14} className="text-accent" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer: live status */}
      <div className="border-t border-gray-100 bg-gray-50/80 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-accent-soft flex items-center justify-center">
            <StepIcon size={16} className="text-accent" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs font-bold text-gray-800">{step.title}</p>
            <p className="text-[11px] text-gray-500">{step.subtitle}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">{'\uAC80\uC0C9 \uC911\uC778 \uC0AC\uB840'}</p>
          <p className="text-base font-bold text-accent tabular-nums" aria-live="polite">
            {recordsScanned.toLocaleString()}<span className="text-xs text-gray-400 ml-0.5">{'\uAC74'}</span>
            {totalCount ? (
              <span className="text-[10px] text-gray-400 ml-1 font-normal"> / {'\uB4F1\uB85D \uD658\uC790'} {totalCount.toLocaleString()}{'\uB0A8'}</span>
            ) : null}
          </p>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// Page
// ────────────────────────────────────────────────────────────────
export default function CaseComparison() {
  const { patientId } = useParams();
  const { count, loading: countLoading } = usePatientCount();
  const [data, setData] = useState(null);
  const [apiDone, setApiDone] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [recordsScanned, setRecordsScanned] = useState(0);

  // Fetch in background
  useEffect(() => {
    if (countLoading || count === 0) return;
    let cancelled = false;
    setApiDone(false);
    (async () => {
      try {
        const res = await api.get(`/case-comparison/${patientId}`);
        if (!cancelled) {
          setData(res.data.data);
          setApiDone(true);
        }
      } catch (e) {
        prodSafeError('CaseComparison.fetch')(e);
        if (!cancelled) setApiDone(true);
      }
    })();
    return () => { cancelled = true; };
  }, [patientId, count, countLoading]);

  // Sequential stepper animation
  useEffect(() => {
    if (countLoading || count === 0) return;
    setActiveStep(0);
    setCompleted(false);
    let timeoutId;
    let stepIdx = 0;

    const advance = () => {
      if (stepIdx >= STEPS.length - 1) {
        const checkDone = () => {
          if (apiDone) setCompleted(true);
          else timeoutId = setTimeout(checkDone, 200);
        };
        checkDone();
        return;
      }
      stepIdx += 1;
      setActiveStep(stepIdx);
      timeoutId = setTimeout(advance, STEPS[stepIdx].duration);
    };

    timeoutId = setTimeout(advance, STEPS[0].duration);
    return () => clearTimeout(timeoutId);
  }, [patientId, count, countLoading, apiDone]);

  // "Records scanned" counter — 실제 등록 환자 수(count) 기반.
  // 가짜 12,000건 대신 실제 DB count 를 목표로 삼아 정직함 유지.
  // 데이터가 적으면 곱셈 없이 그대로, 대량일 때는 정상적으로 증가 표시.
  useEffect(() => {
    if (countLoading || count === 0) return;
    if (completed) return;
    setRecordsScanned(0);
    const target = Math.max(1, count); // 실제 환자 수
    const start = performance.now();
    const totalMs = STEPS.reduce((s, x) => s + x.duration, 0);
    let raf;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / totalMs);
      // Ease-out so it slows near the end
      const eased = 1 - Math.pow(1 - t, 2);
      setRecordsScanned(Math.floor(target * eased));
      if (t < 1 && !completed) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [patientId, count, countLoading, completed]);

  if (countLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
      </div>
    );
  }
  if (count === 0) {
    return <EmptyState title={'\uB4F1\uB85D\uB41C \uD658\uC790\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4'} message={'CSV \uD30C\uC77C\uC744 \uC5C5\uB85C\uB4DC\uD574 \uD658\uC790 \uB370\uC774\uD130\uB97C \uB4F1\uB85D\uD558\uBA74 \uC720\uC0AC \uC0AC\uB840\uB97C \uBD84\uC11D\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.'} />;
  }

  const cases = data?.cases || [];

  return (
    <div className="space-y-6 fade-in w-full">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">{'\uC720\uC0AC \uC0AC\uB840 \uBD84\uC11D \uACB0\uACFC'}</h1>
          <p className="text-sm text-gray-500 mt-2 max-w-2xl">
            {completed
              ? <>{'\uC778\uACF5\uC9C0\uB2A5\uC774 '}<span className="font-semibold text-gray-700">{data?.patient_name}</span>{' \uB2D8\uC758 \uB370\uC774\uD130 \uD3EC\uC778\uD2B8\uB97C \uBD84\uC11D\uD558\uC5EC \uCD5C\uC801\uC758 \uC131\uACF5 \uC0AC\uB840\uB97C \uCC3E\uC558\uC2B5\uB2C8\uB2E4.'}</>
              : <>{'AI\uAC00 \uC601\uAD6C\uC801 \uD658\uC790 \uB370\uC774\uD130\uBCA0\uC774\uC2A4\uB97C \uD0D0\uC0C9\uD558\uACE0 \uC788\uC2B5\uB2C8\uB2E4. \uC7A0\uC2DC\uB9CC \uAE30\uB2E4\uB824\uC8FC\uC138\uC694.'}</>
            }
          </p>
        </div>
        <div className={`w-20 h-20 rounded-full gradient-accent flex items-center justify-center text-white text-4xl font-bold shadow-lg transition-transform ${completed ? '' : 'animate-pulse'}`}>
          A
        </div>
      </div>

      <Stepper activeStep={activeStep} completed={completed} />

      {!completed && (
        <SearchingDeck activeStep={activeStep} recordsScanned={recordsScanned} totalCount={count} />
      )}

      {completed && cases.length > 0 && (
        <>
          <div className="flex items-center justify-between fade-in">
            <h2 className="text-base font-bold text-gray-800 flex items-center gap-2">
              <Sparkles size={16} className="text-accent" aria-hidden="true" />
              {'\uCD5C\uC801\uC758 \uB9E4\uCE6D \uC0AC\uB840'} <span className="text-accent">{'\uCD1D'} {cases.length}{'\uAC74'}</span>
            </h2>
            <p className="text-xs text-gray-400">{'\uC815\uB82C \uAE30\uC900: \uC720\uC0AC\uB3C4 \uC21C'}</p>
          </div>


          <div className="grid grid-cols-3 gap-5">
            {cases.map((c, i) => <CaseCard key={i} c={c} index={i} />)}
          </div>
        </>
      )}

      {completed && cases.length === 0 && (
        <div className="bg-white rounded-xl p-10 border border-gray-200 text-center">
          <p className="text-sm text-gray-500">{'\uC720\uC0AC \uC0AC\uB840\uB97C \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.'}</p>
        </div>
      )}
    </div>
  );
}
