import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine, ReferenceArea, LabelList,
} from 'recharts';
import { FileText, Calendar, User as UserIcon, Phone, CalendarCheck, CalendarClock } from 'lucide-react';
import api from '../api/client';
import RiskBar from '../components/RiskBar';
import { riskColorFor, prodSafeError } from '../theme';

// 6대 합병증 — 순서 고정(공통주의 #2: 신경 → 망막 → 신장 → 심혈관 → 뇌혈관 → 치매).
// 색상은 색각이상 대비(Okabe-Ito) 6색.
const DISEASE_SERIES = [
  { key: 'neuro', label: '말초신경병증', color: '#E69F00' },
  { key: 'retina', label: '망막병증', color: '#0072B2' },
  { key: 'kidney', label: '신장질환', color: '#009E73' },
  { key: 'cardio', label: '심혈관질환', color: '#D55E00' },
  { key: 'cerebro', label: '뇌혈관질환', color: '#CC79A7' },
  { key: 'dementia', label: '치매', color: '#56B4E9' },
];

const LIVER_SERIES = [
  { key: 'GGT', color: '#0072B2' },
  { key: 'ALT', color: '#E69F00' },
  { key: 'AST', color: '#009E73' },
];

// 성별 표기 — 백엔드 normalize_sex 정책(미상/결측을 임의로 여성 처리하지 않음)과 일치.
const sexKo = (s) => (s === 'M' ? '남' : s === 'F' ? '여' : '미상');
// NaN/Infinity 를 null 로 정리 — 표에 'NaN' 이 찍히거나 recharts domain 이 깨지는 것 방지(codex).
const num = (v) => {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const r0 = (v) => { const n = num(v); return n == null ? null : Math.round(n); };
const won = (n) => (n == null ? '—' : Number(n).toLocaleString('ko-KR'));
const ymdFull = (iso) => {
  if (!iso) return '—';
  const [y, m, d] = String(iso).split('T')[0].split('-');
  return `${y}.${m}.${d}`;
};
// X축/표 날짜 라벨
const fmtX = (v) => { const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(v)); return m ? `${m[1]}.${m[2]}.${m[3]}` : v; };

// 실제 혈액검사 수치가 있는 방문 = '검사일'.
//   체중(BMI)만 잰 재방문은 나머지 지표가 최신값으로 근사돼 위험도가 의미 있게 변하지 않으므로
//   통합 표/그래프에서 제외한다(같은 점수 반복 → 오해 유발).
const isExamVisit = (v) => ['hba1c', 'c_peptide', 'cr', 'ggt', 'alt', 'ast'].some((k) => v.measured?.[k] != null);

// ── 공통: 번호 배지 섹션 타이틀 ──
function SectionTitle({ n, children, right }) {
  return (
    <div className="flex items-center justify-between mb-2 gap-2">
      <h3 className="flex items-center gap-1.5 text-[13px] font-bold text-gray-800 min-w-0">
        <span className="w-[18px] h-[18px] rounded-full bg-accent text-white text-[10px] font-bold flex items-center justify-center shrink-0">{n}</span>
        <span className="truncate">{children}</span>
      </h3>
      {right && <span className="text-[10px] text-gray-400 shrink-0">{right}</span>}
    </div>
  );
}

function Card({ children, className = '' }) {
  return <div className={`bg-white rounded-xl border border-gray-100 shadow-sm p-3.5 ${className}`}>{children}</div>;
}

// ── 1) 합병증 위험 통합 표 ──
function RiskMatrixTable({ visits }) {
  return (
    <div className="overflow-auto max-h-[182px]">
      <table className="w-full text-[11px]">
        <thead className="sticky top-0 bg-white">
          <tr className="text-gray-500 border-b border-gray-100">
            <th className="text-left font-medium py-1.5 pr-2 whitespace-nowrap">날짜</th>
            {DISEASE_SERIES.map((d) => (
              <th key={d.key} className="text-center font-medium py-1.5 px-1 whitespace-nowrap">{d.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visits.map((v, i) => (
            <tr key={i} className="border-b border-gray-50 last:border-0">
              <td className="py-1.5 pr-2 text-gray-600 whitespace-nowrap tabular-nums">{fmtX(v.measured_at)}</td>
              {DISEASE_SERIES.map((d) => {
                const cell = v.risk?.[d.key] || {};
                const c = riskColorFor(cell.level);
                return (
                  <td key={d.key} className="text-center py-1.5 px-1 whitespace-nowrap">
                    <span className={`font-bold tabular-nums ${c.textStrong}`}>{r0(cell.score) ?? '—'}</span>
                    {cell.level && (
                      <span className={`ml-1 inline-block px-1 py-px rounded text-[9px] font-medium ${c.badge}`}>{cell.level}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// 우측 세로 범례 — recharts payload 순서를 무시하므로 DISEASE_SERIES 순서로 직접 렌더.
function RightLegend() {
  return (
    <ul className="text-[10px] space-y-[3px] pl-1">
      {DISEASE_SERIES.map((d) => (
        <li key={d.key} className="flex items-center gap-1 whitespace-nowrap">
          <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
          <span className="text-gray-600">{d.label}</span>
        </li>
      ))}
    </ul>
  );
}

// ── 2) 합병증 위험 통합 그래프 ──
function RiskTrendChart({ visits }) {
  const data = visits.map((v) => {
    const row = { month: v.measured_at };
    DISEASE_SERIES.forEach((d) => { row[d.key] = r0(v.risk?.[d.key]?.score); });
    return row;
  });
  const showLabels = data.length <= 6;
  return (
    <div role="img" aria-label="합병증 위험 점수 변화 6종 그래프">
      <ResponsiveContainer width="100%" height={182}>
        <LineChart data={data} margin={{ top: 14, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="month" tickFormatter={fmtX} tick={{ fontSize: 9, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 9, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={30} />
          <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '11px' }} labelFormatter={fmtX} />
          {/* 스펙: 우측 범례. recharts payload 순서 무시 이슈로 커스텀 content 사용 */}
          <Legend layout="vertical" align="right" verticalAlign="middle" content={<RightLegend />} />
          {DISEASE_SERIES.map((d) => (
            <Line key={d.key} type="monotone" dataKey={d.key} name={d.label} stroke={d.color} strokeWidth={1.8} dot={{ r: 2, fill: d.color }} connectNulls isAnimationActive={false}>
              {showLabels && <LabelList dataKey={d.key} position="top" fontSize={8} fill={d.color} />}
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── 3/4/5) 시나리오 카드 ──
const TONE = {
  neglect: { bar: 'bg-gray-50', num: 'text-gray-800', badge: 'bg-gray-400' },
  intensive: { bar: 'bg-emerald-50', num: 'text-emerald-700', badge: 'bg-emerald-500' },
  graduation: { bar: 'bg-indigo-50', num: 'text-indigo-700', badge: 'bg-indigo-500' },
};

function StatChip({ label, value, unit, tone }) {
  return (
    <div className={`${tone.bar} rounded-lg px-1.5 py-1 text-center min-w-0`}>
      <p className="text-[9px] text-gray-500 leading-tight truncate">{label}</p>
      <p className={`text-[12px] font-bold leading-tight ${tone.num} truncate`}>
        {value}{unit && <span className="text-[9px] font-normal text-gray-400 ml-px">{unit}</span>}
      </p>
    </div>
  );
}

function ScenarioBars({ complications }) {
  return (
    <div className="mt-2.5">
      {DISEASE_SERIES.map((d, i) => {
        const c = complications?.[d.key] || {};
        return (
          <div key={d.key} className="flex items-center gap-1.5 py-[2.5px]">
            <span className="w-3.5 h-3.5 rounded-full bg-gray-100 text-gray-500 text-[8px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
            <span className="text-[10px] text-gray-600 w-[64px] shrink-0 truncate">{d.label}</span>
            <div className="flex-1 min-w-0"><RiskBar score={c.score || 0} level={c.level} height="h-1.5" /></div>
            <span className="w-5 text-right text-[10px] text-gray-500 tabular-nums shrink-0">{r0(c.score) ?? '—'}</span>
          </div>
        );
      })}
      <div className="flex justify-between text-[8px] text-gray-300 mt-1" style={{ paddingLeft: '86px', paddingRight: '20px' }}>
        <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
      </div>
    </div>
  );
}

function ScenarioCard({ n, tone, title, stats, extraNode, complications }) {
  const t = TONE[tone];
  return (
    <Card>
      <SectionTitle n={n}>{title}</SectionTitle>
      <div className={`grid gap-1.5 ${extraNode ? 'grid-cols-[1fr_1fr_1.7fr]' : 'grid-cols-4'}`}>
        {stats.map((s) => <StatChip key={s.label} {...s} tone={t} />)}
        {extraNode}
      </div>
      <ScenarioBars complications={complications} />
    </Card>
  );
}

// ── 6) 검사수치 통합 표 ──
const LAB_COLS = [
  ['hba1c', '당화혈색소', '%'],
  ['c_peptide', 'C-peptide', 'ng/mL'],
  ['ggt', 'GGT', 'U/L'],
  ['alt', 'ALT', 'U/L'],
  ['ast', 'AST', 'U/L'],
  ['cr', 'Cr', 'mg/dL'],
];
// 그날 '실제로 측정된' 값만 표시. values 는 LOCF 이월값이라 표에 쓰면 안 잰 날도 잰 것처럼 보인다.
function labVal(v, key) {
  return num(v.measured?.[key]);
}
function LabTable({ visits }) {
  return (
    <div className="overflow-auto max-h-[182px]">
      <table className="w-full text-[11px]">
        <thead className="sticky top-0 bg-white">
          <tr className="text-gray-500 border-b border-gray-100">
            <th className="text-left font-medium py-1.5 pr-2 whitespace-nowrap">날짜</th>
            {LAB_COLS.map(([k, label, unit]) => (
              <th key={k} className="text-right font-medium py-1.5 px-1.5 whitespace-nowrap">
                {label}<span className="block text-[8px] text-gray-300 font-normal">{unit}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visits.map((v, i) => (
            <tr key={i} className="border-b border-gray-50 last:border-0">
              <td className="py-1.5 pr-2 text-gray-600 whitespace-nowrap tabular-nums">{fmtX(v.measured_at)}</td>
              {LAB_COLS.map(([k]) => {
                const val = labVal(v, k);
                return (
                  <td key={k} className="text-right py-1.5 px-1.5 tabular-nums text-gray-800">
                    {val == null ? <span className="text-gray-300">—</span> : (Number.isInteger(val) ? val : Math.round(val * 100) / 100)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 7) 검사수치 추이 (목표선/참고범위 지원) ──
function MetricTrendChart({ data, title, unit, color, refLine, refBand, decimals = 1 }) {
  const points = (data || []).filter((d) => d && d.value != null);
  const showLabels = points.length <= 8;
  const vals = points.map((d) => d.value);
  const extra = [...(refLine != null ? [refLine] : []), ...(refBand || [])];
  const all = [...vals, ...extra];
  const lo = all.length ? Math.min(...all) : 0;
  const hi = all.length ? Math.max(...all) : 1;
  const domain = [Math.max(0, Math.floor(lo) - (lo % 1 === 0 ? 1 : 0)), Math.ceil(hi) + (hi % 1 === 0 ? 1 : 0)];
  return (
    <div>
      <div className="flex items-center justify-between mb-0.5 gap-1">
        <h4 className="text-[11px] font-semibold text-gray-700 truncate">{title} <span className="text-[9px] text-gray-400 font-normal">({unit})</span></h4>
        {refLine != null && <span className="text-[8px] text-emerald-600 shrink-0">목표 {refLine} 이하</span>}
        {refBand && <span className="text-[8px] text-emerald-600 shrink-0">참고 {refBand[0]}~{refBand[1]}</span>}
      </div>
      <ResponsiveContainer width="100%" height={106}>
        <LineChart data={points} margin={{ top: 12, right: 6, left: -4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          {refBand && <ReferenceArea y1={refBand[0]} y2={refBand[1]} fill="#22c55e" fillOpacity={0.08} />}
          {refLine != null && <ReferenceLine y={refLine} stroke="#16a34a" strokeDasharray="4 3" strokeWidth={1.2} />}
          <XAxis dataKey="month" tickFormatter={fmtX} tick={{ fontSize: 8, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
          <YAxis domain={domain} tick={{ fontSize: 8, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={28} />
          <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '11px' }} labelFormatter={fmtX} />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={1.8} dot={{ r: 2.5, fill: color }} connectNulls isAnimationActive={false}>
            {showLabels && <LabelList dataKey="value" position="top" fontSize={8} fill="#6b7280" formatter={(v) => (v == null ? '' : Number(v).toFixed(decimals))} />}
          </Line>
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function LiverTrendChart({ data, hasTrend }) {
  const points = (data || []).filter((d) => d && (d.GGT != null || d.ALT != null || d.AST != null));
  return (
    <div>
      <div className="flex items-center justify-between mb-0.5">
        <h4 className="text-[11px] font-semibold text-gray-700 truncate">간수치 <span className="text-[9px] text-gray-400 font-normal">(GGT / ALT / AST)</span></h4>
        <span className="text-[8px] text-gray-400 shrink-0">ALT·AST ≤40 · GGT ≤50</span>
      </div>
      {hasTrend ? (
        <div role="img" aria-label="간수치 GGT ALT AST 추이 차트">
          <ResponsiveContainer width="100%" height={106}>
            <LineChart data={points} margin={{ top: 12, right: 6, left: -4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="month" tickFormatter={fmtX} tick={{ fontSize: 8, fill: '#9ca3af' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 8, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '11px' }} labelFormatter={fmtX} />
              <Legend wrapperStyle={{ fontSize: '9px' }} iconType="plainline" />
              {LIVER_SERIES.map((s) => (
                <Line key={s.key} type="monotone" dataKey={s.key} name={s.key} stroke={s.color} strokeWidth={1.8} dot={{ r: 2.5, fill: s.color }} connectNulls isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-[106px] flex items-center justify-center text-[10px] text-gray-400 text-center px-2">
          방문별 간수치 실측이 2회 이상 쌓이면<br />추이가 표시됩니다.
        </div>
      )}
    </div>
  );
}

export default function IntegratedReport() {
  const { patientId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    api.get(`/patients/${patientId}/integrated-report`)
      .then((res) => { if (!cancelled) { setData(res.data?.data || null); setError(null); } })
      .catch((e) => { if (!cancelled) { prodSafeError('IntegratedReport.fetch')(e); setError(e); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [patientId, reloadTick]);

  if (loading) {
    return <div className="flex-1 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" /></div>;
  }
  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center py-20">
        <FileText size={32} className="mb-3 text-gray-300" />
        <p className="text-sm text-gray-600 mb-1">통합 리포트를 불러오지 못했습니다</p>
        <button type="button" onClick={() => setReloadTick((t) => t + 1)} className="text-xs text-accent font-semibold hover:underline mt-2">다시 시도</button>
      </div>
    );
  }
  const allVisits = data?.visits || [];
  const p = data?.patient || {};
  if (!data || allVisits.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center text-gray-400 py-20">
        <FileText size={32} className="mb-3" />
        <p className="text-sm">통합 리포트를 생성할 검사 이력이 없습니다.</p>
      </div>
    );
  }

  // 실제 검사 수치가 있는 방문만 표/그래프에 사용 (체중만 잰 재방문 제외).
  //   단 초진(index 0)은 헤더 '첫 검사일'이자 시나리오 3종의 기준이므로 필터와 무관하게 항상 포함한다.
  //   (codex) 안 그러면 초진이 체중만 잰 방문일 때 표 첫 행과 첫 검사일·시나리오 기준이 어긋난다.
  const examVisits = allVisits.filter((v, i) => i === 0 || isExamVisit(v));
  const visits = examVisits.length > 0 ? examVisits : allVisits;
  const skipped = allVisits.length - visits.length;

  const sc = data.scenarios;
  const insufficient = sc?.insufficient;
  const neglect = sc?.neglect;
  const intensive = sc?.intensive;
  const graduation = sc?.graduation;

  const trendMetric = (key) => visits.map((v) => ({ month: v.measured_at, value: num(v.metrics?.[key]) }));
  const trendLiver = visits.map((v) => ({
    month: v.measured_at,
    GGT: num(v.measured?.ggt),
    ALT: num(v.measured?.alt),
    AST: num(v.measured?.ast),
  }));
  const liverHasTrend = Math.max(...['GGT', 'ALT', 'AST'].map((k) => trendLiver.filter((d) => d[k] != null).length)) >= 2;

  return (
    <div className="space-y-2.5 fade-in w-full break-keep">
      {/* 헤더 */}
      <div className="flex items-center gap-2">
        <span className="w-6 h-6 rounded-lg bg-accent-soft flex items-center justify-center"><FileText size={14} className="text-accent" /></span>
        <h2 className="text-[15px] font-bold text-gray-900">통합 리포트</h2>
        <span className="text-[11px] text-gray-400">환자의 날짜별 변화와 초진 기준 시나리오를 한눈에 확인합니다.</span>
      </div>

      {/* 상단 — 환자 식별 카드 (한 줄 압축) */}
      <Card className="!py-2.5">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-9 h-9 rounded-full bg-accent flex items-center justify-center text-white text-sm font-bold shrink-0">{p.name?.[0] || '?'}</div>
          <span className="text-[15px] font-bold text-gray-900">{p.name}</span>
          <span className="text-[10px] text-accent bg-accent-soft rounded-full px-2 py-0.5 font-semibold">{p.chart_no}</span>
          <span className="flex items-center gap-1 text-[11px] text-gray-600"><Calendar size={12} className="text-gray-400" />{ymdFull(p.dob)}</span>
          <span className="flex items-center gap-1 text-[11px] text-gray-600"><UserIcon size={12} className="text-gray-400" />{p.age}세 / {sexKo(p.sex)}</span>
          <span className="flex items-center gap-1 text-[11px] text-gray-600"><Phone size={12} className="text-gray-400" />{p.phone || '—'}</span>
          <div className="h-6 w-px bg-gray-200 mx-1 hidden md:block" />
          <span className="flex items-center gap-1.5 text-[11px]">
            <CalendarCheck size={12} className="text-gray-400" />
            <span className="text-gray-400">첫 검사일</span><b className="text-gray-800">{ymdFull(p.first_exam_date)}</b>
          </span>
          <span className="flex items-center gap-1.5 text-[11px]">
            <CalendarClock size={12} className="text-gray-400" />
            <span className="text-gray-400">최근 검사일</span><b className="text-gray-800">{ymdFull(p.last_exam_date)}</b>
          </span>
          {p.dm_duration != null && (
            <span className="text-[11px] text-gray-500 ml-auto">당뇨 이환기간 <b className="text-gray-800">{p.dm_duration}년</b></span>
          )}
        </div>
      </Card>

      {/* 1 · 2 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2.5">
        <Card>
          <SectionTitle n={1} right={skipped > 0 ? `검사 ${visits.length}회 (체중만 잰 ${skipped}회 제외)` : `검사 ${visits.length}회`}>
            합병증 위험 통합 표
          </SectionTitle>
          <RiskMatrixTable visits={visits} />
          <p className="mt-1 text-[9px] text-gray-400">위험도 등급은 합병증별 개별 기준으로 계산됩니다 (공통 컷오프 미적용).</p>
        </Card>
        <Card>
          <SectionTitle n={2} right="위험 점수 (0~100)">합병증 위험 통합 그래프</SectionTitle>
          <RiskTrendChart visits={visits} />
        </Card>
      </div>

      {/* 3 · 4 · 5 — 초진 기준 시나리오 */}
      {insufficient ? (
        <Card>
          <p className="text-xs text-gray-600 text-center py-3">시나리오 분석에 필요한 초진 검사값이 부족합니다.
            {sc?.missing_required?.length > 0 && <span className="block text-[10px] text-gray-400 mt-1">누락: {sc.missing_required.join(', ')}</span>}
          </p>
        </Card>
      ) : (
        <>
          {data.scenarios_approximate && (
            <p className="text-[10px] text-amber-600 px-1 -mb-1">※ 첫 검사에 전체 검사 스냅샷이 없어, 초진 4지표(HbA1c·C-peptide·Cr·BMI) 외 항목은 최신값으로 근사한 추정입니다.</p>
          )}
          {/* B안: 시나리오는 혈당 관리 궤적이라 지질(Rule7)·혈압(Rule6) 안전망을 제외한다.
              해당 위험은 대시보드에서 그대로 경고되므로 어디를 봐야 하는지 안내한다. */}
          {sc?.meta?.floor_policy_note && (
            <p className="text-[10px] text-gray-400 px-1 -mb-1">※ {sc.meta.floor_policy_note}</p>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-2.5">
            <ScenarioCard
              n={3} tone="neglect" title="초진 ‘현재 수치 유지 시’"
              complications={neglect?.complications}
              stats={[
                { label: '예상 건강수명', value: neglect?.life_expectancy ?? '—', unit: '세' },
                { label: '예상 의료비', value: won(neglect?.annual_cost_man), unit: '만원' },
                { label: '당뇨약 개수', value: `${neglect?.drug_count_before ?? '—'}→${neglect?.drug_count_after ?? '—'}`, unit: '개' },
                { label: '인슐린 맞을 확률', value: neglect?.insulin_probability ?? '—', unit: '%' },
              ]}
            />
            <ScenarioCard
              n={4} tone="intensive" title="초진 ‘집중관리 시’"
              complications={intensive?.complications}
              stats={[
                { label: '예상 건강수명', value: intensive?.life_expectancy ?? '—', unit: '세' },
                { label: '예상 의료비', value: won(intensive?.annual_cost_man), unit: '만원' },
                { label: '당화혈색소', value: `${intensive?.hba1c_before ?? '—'}→${intensive?.hba1c_after ?? '—'}`, unit: '%' },
                { label: 'C-peptide', value: `${intensive?.cpeptide_before ?? '—'}→${intensive?.cpeptide_after ?? '—'}`, unit: '' },
              ]}
            />
            <ScenarioCard
              n={5} tone="graduation" title="초진 ‘졸업 시’"
              complications={graduation?.complications}
              stats={[
                { label: '예상 건강수명', value: graduation?.life_expectancy ?? '—', unit: '세' },
                { label: '예상 의료비', value: won(graduation?.annual_cost_man), unit: '만원' },
              ]}
              extraNode={(
                <div className="bg-indigo-50 rounded-lg px-1.5 py-1">
                  <p className="text-[9px] text-gray-500 leading-tight text-center">졸업 기준값</p>
                  <div className="grid grid-cols-2 gap-x-1">
                    <div className="text-center min-w-0">
                      <p className="text-[8px] text-gray-400 leading-tight truncate">HbA1c / C-peptide</p>
                      <p className="text-[11px] font-bold text-indigo-700 leading-tight truncate">
                        {graduation?.standard_values?.hba1c ?? '—'}% / {graduation?.standard_values?.c_peptide ?? '—'}
                      </p>
                    </div>
                    <div className="text-center min-w-0">
                      <p className="text-[8px] text-gray-400 leading-tight truncate">혈압 / BMI</p>
                      <p className="text-[11px] font-bold text-indigo-700 leading-tight truncate">
                        {graduation?.standard_values?.sbp ?? '—'}/{graduation?.standard_values?.dbp ?? '—'} · {graduation?.standard_values?.bmi ?? '—'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            />
          </div>
        </>
      )}

      {/* 6 · 7 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2.5">
        <Card>
          <SectionTitle n={6} right={`${visits.length}회`}>검사수치 통합 표</SectionTitle>
          <LabTable visits={visits} />
        </Card>
        <Card>
          <SectionTitle n={7} right="당화혈색소 · C-peptide · 간수치">검사수치 통합 그래프</SectionTitle>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <MetricTrendChart data={trendMetric('hba1c')} title="A. 당화혈색소" unit="%" color="#0072B2" refLine={6.5} decimals={1} />
            <MetricTrendChart data={trendMetric('c_peptide')} title="B. C-peptide" unit="ng/mL" color="#009E73" refBand={[1.0, 3.5]} decimals={2} />
            <LiverTrendChart data={trendLiver} hasTrend={liverHasTrend} />
          </div>
        </Card>
      </div>
    </div>
  );
}
