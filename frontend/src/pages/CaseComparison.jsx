import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Check, Database, Filter, Target, TrendingUp, Loader2, GraduationCap, Award, Activity, Info, Search, Cpu, Sparkles, AlertCircle, RotateCcw } from 'lucide-react';
import api, { errorMessage } from '../api/client';
import EmptyState from '../components/EmptyState';
import TrendChart from '../components/TrendChart';
import { prodSafeError, UNITS } from '../theme';

const sexLabel = (s) => (s === 'M' ? '남' : s === 'F' ? '여' : '-');
const fmt = (v, suffix = '') => (v == null ? '-' : `${v}${suffix}`);

// 합병증 표시 순서/라벨 (전/후 위험도 바)
const COMP_ORDER = ['neuro', 'retina', 'kidney', 'cardio', 'cerebro', 'dementia'];
const COMP_LABEL = {
  neuro: '말초신경병증', retina: '망막병증', kidney: '신장질환',
  cardio: '심혈관질환', cerebro: '뇌혈관질환', dementia: '치매',
};

// I18: 모듈 로드 시 1회 평가하면 이후 OS 설정 변경이 반영되지 않아, 컴포넌트 렌더 시점에 평가한다.
function getPrefersReducedMotion() {
  return typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

// 탐색 과정 4단계 (CLAUDE.md PAGE6 스펙)
const STEPS = [
  { num: '01', title: '데이터 수집 및 정제', subtitle: '환자 기본 정보 분석', icon: Database, duration: 1100 },
  { num: '02', title: '핵심 특징 추출', subtitle: '취약 지표·당화혈색소 벡터화', icon: Filter, duration: 1300 },
  { num: '03', title: '유사도 알고리즘 가동', subtitle: '졸업자 사례 최근접 탐색', icon: Target, duration: 1700 },
  { num: '04', title: '상위 사례 확정', subtitle: '검증 및 순위화', icon: TrendingUp, duration: 1100 },
];

// ────────────────────────────────────────────────────────────────
// 탐색 과정 수평 스텝퍼
// ────────────────────────────────────────────────────────────────
function Stepper({ activeStep, completed }) {
  const N = STEPS.length;
  const startPct = 50 / N;
  const spanPct = 100 - startPct * 2;
  const filledPct = completed ? spanPct : (activeStep / (N - 1)) * spanPct;

  return (
    <div className="bg-white rounded-xl p-6 border border-gray-100 shadow-sm">
      <div className="flex items-start justify-between relative">
        <div className="absolute top-6 h-0.5 bg-gray-200 rounded-full" style={{ left: `${startPct}%`, right: `${startPct}%` }} />
        <div
          className="absolute top-6 h-0.5 rounded-full transition-all duration-500"
          style={{ left: `${startPct}%`, width: `${filledPct}%`, backgroundColor: 'var(--db-accent, #6366f1)' }}
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
                    isDone ? 'bg-accent text-white shadow-md'
                      : isActive ? 'bg-accent text-white shadow-lg animate-pulse'
                      : 'bg-gray-100 text-gray-400'
                  }`}
                  style={isActive ? { boxShadow: '0 0 0 4px var(--db-accent-ring, rgba(99,102,241,0.35))' } : undefined}
                >
                  {isActive ? <Loader2 size={18} className="animate-spin" /> : <Icon size={18} />}
                </div>
                {isDone && (
                  <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-green-500 flex items-center justify-center shadow-sm ring-2 ring-white">
                    <Check size={12} className="text-white" />
                  </div>
                )}
              </div>
              <p className={`text-[10px] mt-3 font-medium ${isPending ? 'text-gray-400' : 'text-gray-500'}`}>STEP {step.num}</p>
              <p className={`text-xs font-semibold mt-0.5 text-center ${isPending ? 'text-gray-400' : 'text-gray-800'}`}>{step.title}</p>
              <p className="text-[10px] text-gray-400 mt-0.5 text-center max-w-[140px] leading-tight">{step.subtitle}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// 탐색 모션 — 사방에서 휘날리는 졸업자 고스트 카드 + 중앙 스캐너
//   비전문가/고령 환자에게 'AI가 실제로 많은 기록을 뒤지고 있다'는 느낌을 준다.
// ────────────────────────────────────────────────────────────────
const GHOST_NAMES = ['김O식', '이O희', '박O철', '정O자', '최O민', '강O수', '윤O경', '조O환', '한O진', '서O은', '문O호', '오O정'];
const GHOST_HUES = ['#fef3c7', '#dbeafe', '#dcfce7', '#fee2e2', '#ede9fe', '#cffafe'];

function makeGhost(i) {
  const dir = i % 4; // 0=L→R, 1=R→L, 2=T→B, 3=B→T
  const rand = (a, b) => a + Math.random() * (b - a);
  let txFrom, txTo, tyFrom, tyTo;
  if (dir === 0) { txFrom = '-220%'; txTo = '220%'; tyFrom = `${rand(-60, 60)}%`; tyTo = `${rand(-60, 60)}%`; }
  else if (dir === 1) { txFrom = '220%'; txTo = '-220%'; tyFrom = `${rand(-60, 60)}%`; tyTo = `${rand(-60, 60)}%`; }
  else if (dir === 2) { txFrom = `${rand(-80, 80)}%`; txTo = `${rand(-80, 80)}%`; tyFrom = '-220%'; tyTo = '220%'; }
  else { txFrom = `${rand(-80, 80)}%`; txTo = `${rand(-80, 80)}%`; tyFrom = '220%'; tyTo = '-220%'; }
  return {
    id: i, txFrom, txTo, tyFrom, tyTo,
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
      className="absolute card-fly bg-white/85 backdrop-blur-sm rounded-xl ring-1 ring-indigo-100/70 shadow-[0_10px_28px_-8px_rgba(79,70,229,0.30)] px-3 py-2.5"
      style={{
        '--tx-from': g.txFrom, '--tx-to': g.txTo,
        '--ty-from': g.tyFrom, '--ty-to': g.tyTo,
        '--rot-from': g.rotFrom, '--rot-to': g.rotTo,
        '--fly-dur': g.duration, '--fly-delay': g.delay,
        width: `${g.width}px`,
        left: '50%', top: '50%',
        marginLeft: `-${g.width / 2}px`, marginTop: '-32px',
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
          <p className="text-[8px] text-gray-400">{g.age}세 / {sexLabel(g.sex)}</p>
        </div>
        <span className="text-[8px] font-bold text-emerald-600 bg-emerald-50 rounded px-1 py-0.5">{g.sim}%</span>
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
  const ghostCount = getPrefersReducedMotion() ? 8 : 14;
  const ghosts = useMemo(() => Array.from({ length: ghostCount }, (_, i) => makeGhost(i)), [ghostCount]);
  const step = STEPS[activeStep] || STEPS[0];
  const StepIcon = step.icon;

  return (
    <div className="rounded-2xl border border-indigo-100/60 shadow-sm overflow-hidden relative bg-gradient-to-br from-white via-indigo-50/40 to-white">
      {/* 도트 그리드 배경 (테크 질감) */}
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{ backgroundImage: 'radial-gradient(circle, rgba(99,102,241,0.10) 1px, transparent 1px)', backgroundSize: '22px 22px' }}
      />
      {/* Scanner sweep */}
      <div className="pointer-events-none absolute inset-x-0 top-0 bottom-0 overflow-hidden">
        <div
          className="scanner-bar absolute left-0 right-0 h-32"
          style={{ background: 'linear-gradient(to bottom, transparent, var(--db-accent-soft) 40%, var(--db-accent-soft) 60%, transparent)', opacity: 0.45 }}
        />
      </div>

      <div className="relative" style={{ height: 360 }}>
        {/* 휘날리는 고스트 카드 */}
        {ghosts.map((g) => <GhostCard key={g.id} g={g} />)}

        {/* 중앙 궤도 스캐너 */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="relative w-48 h-48">
            <div className="absolute inset-0 rounded-full border-2 border-dashed orbit-slow" style={{ borderColor: 'var(--db-accent-ring)' }} />
            <div className="absolute inset-6 rounded-full border-2 border-dashed orbit-fast" style={{ borderColor: 'var(--db-accent-ring)' }} />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="absolute w-20 h-20 rounded-full halo-pulse" style={{ backgroundColor: 'var(--db-accent-ring)' }} />
              <div className="absolute w-20 h-20 rounded-full halo-pulse" style={{ backgroundColor: 'var(--db-accent-ring)', animationDelay: '0.7s' }} />
            </div>
            <div className="absolute inset-0 flex items-center justify-center">
              <div
                className="w-20 h-20 rounded-full gradient-accent flex items-center justify-center text-white shadow-2xl"
                style={{ boxShadow: '0 0 50px 8px rgba(99,102,241,0.45), 0 12px 32px rgba(79,70,229,0.40)' }}
              >
                <Search size={32} className="animate-pulse" />
              </div>
            </div>
            <div className="absolute inset-0 orbit-slow">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center"><Cpu size={14} className="text-accent" /></div>
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center"><Database size={14} className="text-accent" /></div>
              <div className="absolute top-1/2 left-0 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center"><Filter size={14} className="text-accent" /></div>
              <div className="absolute top-1/2 right-0 -translate-y-1/2 w-8 h-8 rounded-full bg-white shadow border border-gray-100 flex items-center justify-center"><Sparkles size={14} className="text-accent" /></div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer: 실시간 상태 */}
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
          <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">검색 중인 사례</p>
          <p className="text-base font-bold text-accent tabular-nums" aria-live="polite">
            {recordsScanned.toLocaleString()}<span className="text-xs text-gray-400 ml-0.5">건</span>
            {totalCount ? (
              <span className="text-[10px] text-gray-400 ml-1 font-normal"> / 졸업자 {totalCount.toLocaleString()}명</span>
            ) : null}
          </p>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// 졸업자 유사사례 카드 (라벨/카테고리 없이 동일 양식)
// ────────────────────────────────────────────────────────────────
function GradCaseCard({ c, primary }) {
  const drop = c.hba1c_drop != null ? c.hba1c_drop : null;
  return (
    <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm flex flex-col gap-4 card-settle">
      {/* 헤더 */}
      <div className="flex items-center gap-3">
        <div className={`w-11 h-11 rounded-full flex items-center justify-center text-white ${primary ? 'bg-accent' : 'bg-emerald-600'}`}>
          {primary ? <Activity size={18} /> : <Award size={18} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-gray-800">{c.name}</h3>
            <span className="text-[11px] text-gray-400">{fmt(c.age, '세')} / {sexLabel(c.sex)}</span>
            {c.goal && <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{c.goal}</span>}
          </div>
        </div>
        <span className="bg-green-100 text-green-700 text-[10px] px-2 py-0.5 rounded-full font-semibold shrink-0">
          유사도 {c.similarity}%
        </span>
      </div>

      {/* 치료 전/후 (당화혈색소·C-peptide·치료기간·당뇨약) */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-2">
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">당화혈색소 (전→후)</p>
          <p className="text-sm font-bold text-gray-800">
            {fmt(c.hba1c_before, '%')} <span className="text-gray-300">→</span> <span className="text-emerald-600">{fmt(c.hba1c_after, '%')}</span>
          </p>
          {drop != null && drop > 0 && <p className="text-[10px] text-emerald-600 font-semibold">▼ {drop}%p 감소</p>}
        </div>
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">C-peptide (전→후)</p>
          <p className="text-sm font-bold text-gray-800">
            {c.cpep_before != null && c.cpep_after != null
              ? <>{c.cpep_before} <span className="text-gray-300">→</span> <span className="text-emerald-600">{c.cpep_after}</span></>
              : '-'}
          </p>
        </div>
        {/* eGFR 은 졸업자 raw 데이터셋에 있을 때만 노출 — 신장 회복 사례의 핵심 근거 */}
        {c.egfr_before != null && c.egfr_after != null && (
          <div>
            <p className="text-[10px] text-gray-400 mb-0.5">eGFR (전→후)</p>
            <p className="text-sm font-bold text-gray-800">
              {Math.round(c.egfr_before)} <span className="text-gray-300">→</span>{' '}
              <span className={c.egfr_after > c.egfr_before ? 'text-emerald-600' : 'text-gray-600'}>
                {Math.round(c.egfr_after)}
              </span>
            </p>
            {c.egfr_after > c.egfr_before && (
              <p className="text-[10px] text-emerald-600 font-semibold">▲ {Math.round(c.egfr_after - c.egfr_before)} 개선</p>
            )}
          </div>
        )}
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">치료 기간</p>
          <p className="text-sm font-bold text-gray-800">{fmt(c.treatment_months, '개월')}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">당뇨약 개수</p>
          <p className="text-sm font-bold text-gray-800">{c.dm_med_count != null ? `${c.dm_med_count}개` : '-'}</p>
        </div>
      </div>

      {/* 합병증 위험도 전/후 (데이터 있으면 바, 없으면 보강 대기) */}
      {c.comp_before && c.comp_after ? (
        <div className="border-t border-gray-100 pt-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] text-gray-400">합병증 위험도 변화 (전→후)</p>
            <span className="text-[9px] text-gray-400"><span className="text-red-400">●</span> 이전 <span className="text-emerald-500">●</span> 이후</span>
          </div>
          <div className="space-y-1.5">
            {COMP_ORDER.map((k) => {
              const b = c.comp_before[k]; const a = c.comp_after[k];
              if (b == null && a == null) return null;
              return (
                <div key={k}>
                  <div className="flex justify-between text-[10px] text-gray-500 mb-0.5">
                    <span>{COMP_LABEL[k]}</span>
                    <span className="tabular-nums">{b ?? '-'} → <span className="text-emerald-600 font-semibold">{a ?? '-'}</span></span>
                  </div>
                  <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    {(() => {
                      // I18: 두 바를 겹쳐 그릴 때 긴 쪽을 아래에 → 악화(after ≥ before) 시에도
                      //   빨간(이전) 바가 완전히 가려지지 않고 짧은 쪽이 위에 보인다.
                      const bw = Math.min(100, b ?? 0);
                      const aw = Math.min(100, a ?? 0);
                      const beforeBar = <div key="before" className="absolute h-1.5 rounded-full bg-red-300" style={{ width: `${bw}%` }} />;
                      const afterBar = <div key="after" className="absolute h-1.5 rounded-full bg-emerald-500" style={{ width: `${aw}%` }} />;
                      return bw >= aw ? [beforeBar, afterBar] : [afterBar, beforeBar];
                    })()}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : c.complications_pending ? (
        <div className="text-[10px] text-gray-400 border border-dashed border-gray-200 rounded-lg px-3 py-2 flex items-center gap-1.5">
          <Info size={11} /> 합병증 위험도 전/후 변화는 졸업자 데이터 보강 후 표시됩니다.
        </div>
      ) : null}

      {/* 의료비/건강수명 — 증감 표현 */}
      <div className="grid grid-cols-2 gap-3 pt-1 border-t border-gray-100">
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">예상 의료비</p>
          <p className="text-base font-bold text-emerald-600">−{fmt(c.cost_saving_man, '만원')}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-400 mb-0.5">기대 건강수명</p>
          <p className="text-base font-bold text-emerald-600">+{fmt(c.healthy_years_gain, '세')}</p>
        </div>
      </div>
    </div>
  );
}

export default function CaseComparison() {
  const { patientId } = useParams();
  const [data, setData] = useState(null);
  // 조회 실패(404/인증/서버장애)를 '졸업자 데이터 없음'(정상 빈 상태)과 구분하기 위한 에러 상태
  const [loadError, setLoadError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [apiDone, setApiDone] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [recordsScanned, setRecordsScanned] = useState(0);
  const apiDoneRef = useRef(false);
  useEffect(() => { apiDoneRef.current = apiDone; }, [apiDone]);
  const targetRef = useRef(208);   // 카운터 목표(졸업자 수) — 데이터 로드 시 실수치로 갱신
  useEffect(() => { if (data?.graduate_count != null) targetRef.current = data.graduate_count; }, [data?.graduate_count]);

  // 데이터 fetch
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null); setApiDone(false); setLoadError(null);
    apiDoneRef.current = false;
    api.get(`/case-comparison/${patientId}`)
      .then((res) => { if (!cancelled) setData(res.data?.data || {}); })
      .catch((e) => {
        if (cancelled) return;
        prodSafeError('CaseComparison')(e);
        // 이전에는 모든 오류를 {} 로 바꿔 '사례 없음' 으로 표시했다 → 장애를 빈 상태로 오인.
        setLoadError(errorMessage(e, '유사 사례를 불러오지 못했습니다.'));
        setData(null);
      })
      .finally(() => { if (!cancelled) setApiDone(true); });
    return () => { cancelled = true; };
  }, [patientId, reloadKey]);

  // 탐색 과정 스텝 애니메이션 — 4단계 진행 후 API 완료되면 결과 공개
  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveStep(0); setCompleted(false);
    let timeoutId; let stepIdx = 0;
    const advance = () => {
      if (!active) return;
      if (stepIdx >= STEPS.length - 1) {
        const checkDone = () => {
          if (!active) return;
          if (apiDoneRef.current) setCompleted(true);
          else timeoutId = setTimeout(checkDone, 150);
        };
        checkDone();
        return;
      }
      stepIdx += 1;
      setActiveStep(stepIdx);
      timeoutId = setTimeout(advance, STEPS[stepIdx].duration);
    };
    timeoutId = setTimeout(advance, STEPS[0].duration);
    return () => { active = false; clearTimeout(timeoutId); };
  }, [patientId]);

  // '검색 중인 사례' 카운터 — 졸업자 수(targetRef)를 목표로 ease-out 증가.
  //   target 을 ref 로 읽어 데이터 로드 시 재시작 글리치 없이 실수치 반영.
  useEffect(() => {
    if (completed) return;
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRecordsScanned(0);
    const start = performance.now();
    const totalMs = STEPS.reduce((s, x) => s + x.duration, 0);
    let raf;
    const tick = (now) => {
      if (!active) return;
      const t = Math.min(1, (now - start) / totalMs);
      const eased = 1 - Math.pow(1 - t, 2);
      setRecordsScanned(Math.floor(Math.max(1, targetRef.current) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { active = false; cancelAnimationFrame(raf); };
  }, [patientId, completed]);

  const cases = data?.cases || [];
  const patient = data?.patient || {};
  const graduateCount = data?.graduate_count ?? null;
  // 항목6(a): 환자 본인의 통합 데이터 추이 (BMI/C-peptide/HbA1c)
  const tlSeries = (key) => (data?.timeline || []).map((t) => ({
    month: t.date ? new Date(t.date).toLocaleDateString('ko-KR', { year: '2-digit', month: 'short' }) : '',
    value: t[key],
  }));

  return (
    <div className="fade-in w-full break-keep max-w-5xl mx-auto space-y-6">
      {/* 헤더 (A 일러스트·부제 제거) */}
      <div>
        <h1 className="text-lg font-bold text-gray-800 flex items-center gap-2">
          <GraduationCap size={20} className="text-accent" /> 유사 사례 분석 결과
        </h1>
      </div>

      {/* 탐색 과정 스텝퍼 */}
      <Stepper activeStep={activeStep} completed={completed} />

      {/* 탐색 중 — 휘날리는 고스트 카드 모션 */}
      {!completed && (
        <SearchingDeck activeStep={activeStep} recordsScanned={recordsScanned} totalCount={graduateCount} />
      )}

      {/* 결과 — 탐색 완료 후 공개 */}
      {completed && (
        loadError ? (
          // 조회 실패: 빈 상태(업로드 안내)와 구분해 오류 + 재시도 제공
          <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center">
            <AlertCircle size={28} className="text-red-500 mx-auto mb-3" aria-hidden="true" />
            <p className="text-sm font-bold text-red-700 mb-1">유사 사례를 불러오지 못했습니다</p>
            <p className="text-xs text-red-600 mb-4">{loadError}</p>
            <button
              onClick={() => setReloadKey((k) => k + 1)}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-white border border-red-300 text-red-700 text-xs font-semibold rounded-lg hover:bg-red-100 transition-colors"
            >
              <RotateCcw size={12} aria-hidden="true" /> 다시 시도
            </button>
          </div>
        ) : !data ? (
          <div className="bg-white rounded-xl p-10 border border-dashed border-indigo-200 text-center">
            <Loader2 size={28} className="text-accent animate-spin mx-auto mb-3" aria-hidden="true" />
            <p className="text-sm text-gray-500">유사 사례를 다시 불러오는 중...</p>
          </div>
        ) : cases.length === 0 ? (
          <EmptyState
            icon="users"
            title="유사 졸업자 사례가 없습니다"
            message={data?.data_note || '설정에서 졸업자 데이터를 업로드하세요.'}
            ctaTo="/settings"
            ctaLabel="설정에서 졸업자 엑셀 업로드"
          />
        ) : (
          <div className="fade-in space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {cases.map((c, i) => (
                <GradCaseCard key={c.card_type + i} c={c} primary={i === 0} />
              ))}
            </div>
            {data?.data_note && (
              <p className="text-[11px] text-gray-400 flex items-start gap-1.5">
                <Info size={12} className="mt-0.5 shrink-0" /> {data.data_note}
              </p>
            )}
            {(data?.timeline?.length || 0) >= 2 && (
              <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
                <h3 className="text-sm font-bold text-gray-800 mb-1">통합 데이터 추이</h3>
                <p className="text-[11px] text-gray-400 mb-4">{patient.name} 님의 BMI · C-peptide · 당화혈색소 변화</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <TrendChart data={tlSeries('bmi')} unit={UNITS.bmi} color="var(--color-accent, #6366f1)" title="BMI" />
                  <TrendChart data={tlSeries('c_peptide')} unit={UNITS.cpeptide} color="var(--color-accent, #6366f1)" title="C-peptide" />
                  <TrendChart data={tlSeries('hba1c')} unit={UNITS.percent} color="var(--color-accent, #6366f1)" title="HbA1c" />
                </div>
              </div>
            )}
          </div>
        )
      )}
    </div>
  );
}
