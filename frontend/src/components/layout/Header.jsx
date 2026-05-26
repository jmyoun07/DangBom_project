import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Stethoscope } from 'lucide-react';
import axios from 'axios';

// /health 는 /api/v1 prefix 가 없으므로 baseURL 우회
const HEALTH_URL = import.meta.env.DEV ? 'http://localhost:8000/health' : '/health';

const PAGE_TITLES = {
  '/home': { title: 'CSV 데이터 업로드', subtitle: '환자 데이터를 불러와 분석을 시작하세요' },
  '/dashboard': { title: '환자 대시보드', subtitle: '환자를 선택해 합병증 위험을 분석하세요' },
  '/patients': { title: '환자 목록 관리', subtitle: '등록된 환자 데이터를 확인하고 관리합니다' },
  '/settings': { title: '설정', subtitle: '프로그램 환경설정 및 데이터 관리' },
};

function resolveTitle(pathname) {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  if (pathname.startsWith('/dashboard/')) return { title: '환자 대시보드', subtitle: '합병증 위험 영역별 현황' };
  if (pathname.startsWith('/patients/')) return { title: '환자 상세 정보', subtitle: '검사 수치 및 AI 예측 결과' };
  if (pathname.startsWith('/risk-analysis/')) return { title: '시나리오 분석', subtitle: 'C-peptide / HbA1c 시뮬레이션' };
  if (pathname.startsWith('/case-comparison/')) return { title: '유사 사례 비교', subtitle: 'AI 기반 성공 사례 매칭' };
  return { title: 'DB-care', subtitle: '' };
}

const HEALTH_INTERVAL_MS = 30_000;

// 'unknown' | 'ok' | 'degraded' | 'down'
function StatusIndicator({ status, latencyMs }) {
  const map = {
    ok:        { color: 'bg-emerald-500', ring: 'bg-emerald-400', label: '\uC2DC\uC2A4\uD15C \uC815\uC0C1', pulse: true },
    degraded:  { color: 'bg-amber-500',   ring: 'bg-amber-400',   label: '\uC751\uB2F5 \uC9C0\uC5F0', pulse: true },
    down:      { color: 'bg-red-500',     ring: 'bg-red-400',     label: '\uC11C\uBC84 \uC5F0\uACB0 \uC2E4\uD328', pulse: false },
    unknown:   { color: 'bg-gray-300',    ring: 'bg-gray-200',    label: '\uC0C1\uD0DC \uD655\uC778 \uC911', pulse: false },
  };
  const s = map[status] || map.unknown;
  const tooltip = latencyMs != null && status === 'ok'
    ? `${s.label} \u00B7 ${latencyMs}ms`
    : s.label;

  return (
    <div
      className="hidden md:flex items-center gap-2 text-xs text-gray-500"
      role="status"
      aria-live="polite"
      aria-label={tooltip}
      title={tooltip}
    >
      <span className="relative flex w-2 h-2" aria-hidden="true">
        {s.pulse && (
          <span className={`absolute inline-flex h-full w-full rounded-full ${s.ring} opacity-60 animate-ping`} />
        )}
        <span className={`relative inline-flex w-2 h-2 rounded-full ${s.color}`} />
      </span>
      <span className="tabular-nums">{s.label}</span>
    </div>
  );
}

export default function Header() {
  const { pathname } = useLocation();
  const { title, subtitle } = resolveTitle(pathname);
  const [health, setHealth] = useState({ status: 'unknown', latencyMs: null });

  useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      const start = performance.now();
      try {
        const res = await axios.get(HEALTH_URL, { timeout: 4000 });
        const latency = Math.round(performance.now() - start);
        if (cancelled) return;
        const ok = res.status >= 200 && res.status < 300;
        setHealth({
          status: ok ? (latency > 1500 ? 'degraded' : 'ok') : 'down',
          latencyMs: latency,
        });
      } catch {
        if (!cancelled) setHealth({ status: 'down', latencyMs: null });
      }
    };
    ping();
    const t = setInterval(ping, HEALTH_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  return (
    <header className="h-16 w-full bg-white/95 backdrop-blur border-b border-gray-100 flex items-center justify-between pl-16 pr-6 xl:pl-6 shrink-0 sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg gradient-accent flex items-center justify-center shadow-sm">
          <Stethoscope size={18} className="text-white" strokeWidth={2.2} aria-hidden="true" />
        </div>
        <div>
          <p className="text-sm font-bold text-gray-900 leading-tight tracking-tight">{title}</p>
          {subtitle && <p className="text-[11px] text-gray-400 leading-tight mt-0.5">{subtitle}</p>}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <StatusIndicator status={health.status} latencyMs={health.latencyMs} />
        <span className="text-[11px] text-gray-400 font-mono">v2.1.6</span>
      </div>
    </header>
  );
}
