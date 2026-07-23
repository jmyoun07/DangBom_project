import { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate, NavLink } from 'react-router-dom';
import { LayoutDashboard, User as UserIcon, Activity, GitCompare, History, FileBarChart, ArrowLeft, ChevronRight } from 'lucide-react';
import api from '../../api/client';
import { pushRecentPatient } from '../../hooks/useRecentPatients';
import { sexKo } from '../../theme';
// Which routes this bar applies to — Sidebar 와 단일 소스 공유 (utils/patientRoutes.js)
import { extractPatientContext as extractContext } from '../../utils/patientRoutes';

const TABS = [
  { key: 'dashboard',       label: '\uB300\uC2DC\uBCF4\uB4DC',      icon: LayoutDashboard, toPath: (id) => `/dashboard/${id}` },
  { key: 'patients',        label: '\uC0C1\uC138 \uC815\uBCF4',      icon: UserIcon,         toPath: (id) => `/patients/${id}` },
  { key: 'exam-history',    label: '\uAC80\uC0AC \uC774\uB825',      icon: History,          toPath: (id) => `/exam-history/${id}` },
  { key: 'report',          label: '\uD1B5\uD569 \uB9AC\uD3EC\uD2B8',  icon: FileBarChart,     toPath: (id) => `/report/${id}` },
  { key: 'risk-analysis',   label: '\uC2DC\uB098\uB9AC\uC624 \uBD84\uC11D', icon: Activity,   toPath: (id) => `/risk-analysis/${id}` },
  { key: 'case-comparison', label: '\uC720\uC0AC \uC0AC\uB840',       icon: GitCompare,     toPath: (id) => `/case-comparison/${id}` },
];

// Tiny per-session cache so we don't refetch on every route change.
// 캐시 키: patientId. 환자 데이터 수정 시 'dbcare:patient-updated' 이벤트로 무효화 (I1).
const patientCache = new Map();

// 외부에서 캐시 무효화 트리거 (예: PatientDetail 저장 후)
//   notify:false → 캐시만 비우고 재조회 이벤트는 쏘지 않는다 (삭제된 환자용 — 404 재조회 방지)
// eslint-disable-next-line react-refresh/only-export-components
export function invalidatePatientContextCache(patientId, { notify = true } = {}) {
  if (patientId == null) {
    patientCache.clear();
  } else {
    patientCache.delete(String(patientId));
  }
  if (notify && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('dbcare:patient-updated', {
      detail: { patientId: patientId == null ? null : String(patientId) }
    }));
  }
}

export default function PatientContextBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const ctx = extractContext(location.pathname);
  const [patient, setPatient] = useState(null);
  const [refreshTick, setRefreshTick] = useState(0);
  // I20: 마지막으로 소비(재조회 반영)한 tick — `refreshTick === 0` 고정 비교는 수정 이벤트 1회 후
  //   캐시가 영구 무력화되던 버그가 있어, 새 tick 일 때만 캐시를 건너뛰도록 한다.
  const lastConsumedTickRef = useRef(0);

  // 외부 update 이벤트 수신 → 본인 환자 캐시면 다시 fetch
  useEffect(() => {
    const onUpdate = (e) => {
      const updatedId = e?.detail?.patientId;
      if (updatedId == null || (ctx && updatedId === String(ctx.patientId))) {
        if (ctx) patientCache.delete(String(ctx.patientId));
        setRefreshTick((t) => t + 1);
      }
    };
    window.addEventListener('dbcare:patient-updated', onUpdate);
    return () => window.removeEventListener('dbcare:patient-updated', onUpdate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx?.patientId]);

  useEffect(() => {
    if (!ctx) { setPatient(null); return; }
    const cached = patientCache.get(ctx.patientId);
    if (cached && refreshTick === lastConsumedTickRef.current) { setPatient(cached); pushRecentPatient(cached); return; }
    lastConsumedTickRef.current = refreshTick;

    let cancelled = false;
    (async () => {
      try {
        const res = await api.get(`/patients/${ctx.patientId}`);
        const d = res.data?.data;
        const flat = d?.patient ? { ...d.patient } : d;
        if (!cancelled && flat?.id) {
          patientCache.set(ctx.patientId, flat);
          setPatient(flat);
          pushRecentPatient(flat);
        }
      } catch {
        if (!cancelled) setPatient(null);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx?.patientId, refreshTick]);

  if (!ctx) return null;

  return (
    <div className="sticky top-16 z-20 bg-white border-b border-gray-100 shadow-[0_1px_0_rgba(15,23,42,0.02)]">
      <div className="px-6 py-3 flex items-center gap-4">
        {/* Back to patient list */}
        <button
          onClick={() => navigate('/patients')}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 transition-colors shrink-0"
          title={'\uD658\uC790 \uBAA9\uB85D\uC73C\uB85C'}
        >
          <ArrowLeft size={14} />
          <span className="hidden md:inline">{'\uBAA9\uB85D'}</span>
        </button>

        <div className="h-5 w-px bg-gray-200 shrink-0" />

        {/* Patient identity */}
        <div className="flex items-center gap-3 shrink-0 min-w-0">
          <div className="w-9 h-9 rounded-full bg-accent flex items-center justify-center text-white text-xs font-bold shrink-0">
            {patient?.name?.[0] || '?'}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-sm font-bold text-gray-900 truncate">
                {patient?.name || <span className="inline-block h-3.5 w-20 bg-gray-100 rounded animate-pulse" />}
              </p>
              {patient && (
                <span className="inline-flex items-center gap-1 text-[10px] text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded-full border border-gray-100">
                  {sexKo(patient.sex)} · {patient.age}{'\uC138'}
                </span>
              )}
            </div>
            <p className="text-[11px] text-gray-500 truncate">
              {patient?.chart_no || `ID #${ctx.patientId}`}
            </p>
          </div>
        </div>

        <div className="h-5 w-px bg-gray-200 shrink-0 hidden lg:block" />

        {/* Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto min-w-0 flex-1">
          {/* eslint-disable-next-line no-unused-vars -- Icon은 아래 <Icon /> JSX에서 사용됨 (react plugin 미설정으로 미인식) */}
          {TABS.map(({ key, label, icon: Icon, toPath }) => (
            <NavLink
              key={key}
              to={toPath(ctx.patientId)}
              end={false}
              className={() =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                  ctx.section === key
                    ? 'bg-accent-soft text-accent'
                    : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                }`
              }
            >
              <Icon size={13} />
              {label}
            </NavLink>
          ))}
        </div>

        {/* Next-step hint */}
        {ctx.section === 'dashboard' && (
          <button
            onClick={() => navigate(`/risk-analysis/${ctx.patientId}`)}
            className="hidden md:flex items-center gap-1 text-[11px] text-accent hover:underline shrink-0"
          >
            {'\uC2DC\uB098\uB9AC\uC624 \uBD84\uC11D \uC73C\uB85C'} <ChevronRight size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
