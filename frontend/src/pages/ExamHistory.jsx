import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ClipboardCheck, History, ChartLine, HeartPulse } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import api from '../api/client';
import TrendChart from '../components/TrendChart';
import { UNITS, riskColorFor, prodSafeError, sexKo } from '../theme';

// 간수치 3종 — 색각 이상 대비(Okabe-Ito 계열) 구분색
const LIVER_SERIES = [
  { key: 'GGT', color: '#E69F00' },
  { key: 'ALT', color: '#0072B2' },
  { key: 'AST', color: '#009E73' },
];

// 간수치(GGT·ALT·AST) 다중선 추이 — TrendChart 와 동일한 플랫 스타일.
function LiverTrendChart({ data }) {
  const points = (data || []).filter((d) => d && (d.GGT != null || d.ALT != null || d.AST != null));
  const fmtX = (v) => { const m = /^(\d{4})-(\d{1,2})/.exec(String(v)); return m ? `'${m[1].slice(2)}.${parseInt(m[2], 10)}` : v; };
  return (
    <div className="bg-white rounded-xl p-4 border border-gray-100">
      <h4 className="text-sm font-semibold text-gray-700 mb-2">간수치 <span className="text-[11px] text-gray-400 font-normal">(GGT·ALT·AST, U/L)</span></h4>
      <div role="img" aria-label="간수치 GGT ALT AST 추이 차트">
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={points} margin={{ top: 5, right: 5, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="month" tickFormatter={fmtX} tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={30} />
            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '12px' }} labelFormatter={fmtX} />
            <Legend wrapperStyle={{ fontSize: '11px' }} iconType="plainline" />
            {LIVER_SERIES.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.key} stroke={s.color} strokeWidth={2} dot={{ r: 3, fill: s.color }} connectNulls isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[10px] text-gray-400">정상: ALT·AST ≤40 · GGT ≤50 U/L</p>
    </div>
  );
}

// 4사분면 하단 합병증 (대시보드와 동일 순서: 미세혈관3 → 대혈관2 → 치매)
const COMP = [
  ['neuro', '당뇨병성 말초신경병증'],
  ['retina', '당뇨병성 망막병증'],
  ['kidney', '당뇨병성 신장질환'],
  ['cardio', '당뇨병성 심혈관질환'],
  ['cerebro', '당뇨병성 뇌혈관질환'],
  ['dementia', '당뇨병성 치매'],
];

// 검사 수치 패널 (현재/비교 박스 공통). key, 라벨, 단위, 개선방향(down=낮을수록 좋음 / up=높을수록)
const PANEL = [
  ['hba1c', '당화혈색소', '%', 'down'],
  ['fbg', '공복혈당', 'mg/dL', 'down'],
  ['c_peptide', 'C-peptide', 'ng/mL', 'up'],
  ['cr', '크레아티닌', 'mg/dL', 'down'],
  ['bmi', 'BMI', 'kg/m²', 'down'],
  ['sbp', '수축기혈압', 'mmHg', 'down'],
  ['dbp', '이완기혈압', 'mmHg', 'down'],
  ['total_cholesterol', '총콜레스테롤', 'mg/dL', 'down'],
  ['triglycerides', '중성지방', 'mg/dL', 'down'],
  ['hdl', 'HDL', 'mg/dL', 'up'],
];

const ymd = (iso) => {
  if (!iso) return '--';
  const [y, m, d] = String(iso).split('-');
  return `${String(y).slice(2)}.${m}.${d}`;
};
const num = (v) => (v == null || v === '' ? null : Number(v));
const fmt = (v) => { const n = num(v); return n == null ? '—' : (Number.isInteger(n) ? n : Math.round(n * 100) / 100); };

function LevelText({ level }) {
  if (!level) return <span className="text-gray-400">—</span>;
  const c = riskColorFor(level);
  return <span className={`${c.textStrong} font-medium`}>{level}</span>;
}

// 개선방향 대비 화살표 (현재값이 비교값 대비 좋아졌으면 초록↓/↑)
function Delta({ cur, prev, dir }) {
  const c = num(cur), p = num(prev);
  if (c == null || p == null || c === p) return null;
  const better = dir === 'down' ? c < p : c > p;
  const up = c > p;
  return (
    <span className={`ml-1 text-[10px] ${better ? 'text-emerald-600' : 'text-red-500'}`}>
      {up ? '▲' : '▼'}{Math.abs(Math.round((c - p) * 100) / 100)}
    </span>
  );
}

function ValuePanel({ visit, compareVisit }) {
  const vals = visit?.values || {};
  return (
    <table className="w-full text-sm">
      <tbody>
        {PANEL.map(([key, label, unit, dir]) => (
          <tr key={key} className="border-b border-gray-50 last:border-0">
            <td className="py-1.5 text-gray-500 text-xs">{label}</td>
            <td className="py-1.5 text-right font-semibold text-gray-800 tabular-nums">
              {fmt(vals[key])}
              {unit && vals[key] != null && <span className="text-[10px] text-gray-400 font-normal ml-0.5">{unit}</span>}
              {compareVisit && <Delta cur={vals[key]} prev={compareVisit.values?.[key]} dir={dir} />}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ExamHistory() {
  const { patientId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [compareIdx, setCompareIdx] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    api.get(`/patients/${patientId}/visits`)
      .then((res) => { if (!cancelled) { setData(res.data?.data || null); setCompareIdx(0); setError(null); } })
      .catch((e) => { if (!cancelled) { prodSafeError('ExamHistory.fetch')(e); setError(e); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [patientId, reloadTick]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
      </div>
    );
  }
  // v2.2.9 (#11): fetch 실패/타임아웃을 '이력 없음'과 구분하고 재시도 제공.
  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center py-20">
        <History size={32} className="mb-3 text-gray-300" />
        <p className="text-sm text-gray-600 mb-1">검사 이력을 불러오지 못했습니다</p>
        <p className="text-xs text-gray-400 mb-4">서버 응답이 없거나 지연되었습니다. 데이터가 사라진 것은 아닙니다.</p>
        <button
          type="button"
          onClick={() => setReloadTick((t) => t + 1)}
          className="text-xs text-accent font-semibold hover:underline"
        >
          다시 시도
        </button>
      </div>
    );
  }
  const visits = data?.visits || [];
  if (!data || visits.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center text-gray-400 py-20">
        <History size={32} className="mb-3" />
        <p className="text-sm">검사 이력이 없습니다.</p>
      </div>
    );
  }

  const current = visits[visits.length - 1];
  const compare = visits[Math.min(compareIdx, visits.length - 1)];

  // 추이 데이터 (260617 스펙: 당화혈색소·C-peptide·간수치 3종만).
  //   HbA1c·C-peptide 는 방문별 실측(metrics). 간수치(GGT/ALT/AST)는 스냅샷 방문에만 존재.
  const trendMetric = (key) => visits.map((v) => ({ month: v.measured_at, value: v.metrics?.[key] }));
  //   measured = 그날 실측만. values 는 LOCF 이월값이라 추이에 쓰면 안 잰 날도 잰 것처럼 보인다.
  const trendLiver = visits.map((v) => ({
    month: v.measured_at,
    GGT: num(v.measured?.ggt),
    ALT: num(v.measured?.alt),
    AST: num(v.measured?.ast),
  }));
  // 추이(선)가 실제로 그려지려면 한 계열이라도 실측점 ≥2 필요. (방문A=GGT만·방문B=ALT만 이면
  //   '값 있는 방문' 은 2건이지만 어느 계열도 2점이 안 돼 선이 안 그려지므로 계열별로 카운트)
  const liverSeriesMax = Math.max(
    ...['GGT', 'ALT', 'AST'].map((k) => trendLiver.filter((d) => d[k] != null).length)
  );
  const liverPoints = trendLiver.filter((d) => d.GGT != null || d.ALT != null || d.AST != null).length;
  const liverHasTrend = liverSeriesMax >= 2;

  return (
    <div className="space-y-4 fade-in w-full break-keep">
      {/* 헤더 */}
      <div className="flex items-center gap-3 bg-white rounded-xl border border-gray-100 shadow-sm px-5 py-3">
        <div className="w-10 h-10 rounded-full bg-accent flex items-center justify-center text-white font-bold">
          {data.patient?.name?.[0] || '?'}
        </div>
        <div>
          <div className="text-base font-bold text-gray-900">
            {data.patient?.name} <span className="text-xs text-gray-400 font-normal">{data.patient?.chart_no} · {sexKo(data.patient?.sex)} {data.patient?.age}세</span>
          </div>
          <div className="text-xs text-gray-500">총 {visits.length}회 방문 · 초진 {ymd(visits[0].measured_at)} ~ 최근 {ymd(current.measured_at)}</div>
        </div>
      </div>

      {/* 십자가 4등분 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 좌상 — 현재 검사 수치 */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="flex items-center gap-1.5 text-sm font-bold text-gray-700"><ClipboardCheck size={15} className="text-accent" />현재 검사 수치</h3>
            <span className="text-xs text-gray-400">{current.visit_type} {ymd(current.measured_at)}</span>
          </div>
          <ValuePanel visit={current} compareVisit={compare} />
          <p className="mt-2 text-[10px] text-gray-400">화살표 = 비교일 대비 변화 (초록=호전)</p>
        </div>

        {/* 우상 — 비교 대상 */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3 gap-2">
            <h3 className="flex items-center gap-1.5 text-sm font-bold text-gray-700 shrink-0"><History size={15} className="text-accent" />비교 대상</h3>
            <select
              value={compareIdx}
              onChange={(e) => setCompareIdx(Number(e.target.value))}
              className="text-xs border border-gray-200 rounded-lg px-2 py-1 accent-input max-w-[60%]"
            >
              {visits.slice(0, -1).map((v, i) => (
                <option key={i} value={i}>{v.visit_type} {ymd(v.measured_at)}</option>
              ))}
              {visits.length === 1 && <option value={0}>{current.visit_type} {ymd(current.measured_at)}</option>}
            </select>
          </div>
          <ValuePanel visit={compare} />
          {!compare?.has_snapshot && (
            <p className="mt-2 text-[10px] text-amber-600 leading-tight">이 방문은 핵심 4지표(HbA1c·C-peptide·Cr·BMI)만 실측 · 그 외는 최신값 기준입니다.</p>
          )}
        </div>

        {/* 좌하 — 핵심 수치 추이 (260617 스펙: 당화혈색소·C-peptide·간수치 3종) */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <h3 className="flex items-center gap-1.5 text-sm font-bold text-gray-700 mb-3"><ChartLine size={15} className="text-accent" />핵심 수치 추이</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TrendChart data={trendMetric('hba1c')} unit={UNITS.hba1c} title="당화혈색소" maxPoints={12} />
            <TrendChart data={trendMetric('c_peptide')} unit={UNITS.cpeptide} title="C-peptide" maxPoints={12} />
          </div>
          <div className="mt-3">
            {liverHasTrend ? (
              <LiverTrendChart data={trendLiver} />
            ) : (
              <div className="bg-white rounded-xl p-4 border border-gray-100">
                <h4 className="text-sm font-semibold text-gray-700 mb-1">간수치 <span className="text-[11px] text-gray-400 font-normal">(GGT·ALT·AST)</span></h4>
                <p className="text-[11px] text-gray-400 leading-tight">방문별 실측이 쌓이면 추이가 표시됩니다. (현재 {liverPoints}건)</p>
              </div>
            )}
          </div>
        </div>

        {/* 우하 — 합병증 위험도 변화 */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="flex items-center gap-1.5 text-sm font-bold text-gray-700"><HeartPulse size={15} className="text-accent" />합병증 위험도 변화</h3>
            <span className="text-[11px] text-gray-400">{ymd(compare.measured_at)} → {ymd(current.measured_at)}</span>
          </div>
          <div className="flex flex-col divide-y divide-gray-50">
            {COMP.map(([key, label]) => (
              <div key={key} className="flex items-center justify-between py-2 text-sm">
                <span className="text-gray-700">{label}</span>
                <span className="flex items-center gap-2">
                  <LevelText level={compare.risk?.[key]?.level} />
                  <span className="text-gray-300 text-xs">→</span>
                  <LevelText level={current.risk?.[key]?.level} />
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
