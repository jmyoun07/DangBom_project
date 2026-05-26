import { useEffect, useState } from 'react';
import { NavLink, useLocation, Link } from 'react-router-dom';
import { Home, LayoutDashboard, Users, Activity, GitCompare, Settings, Clock, Lock, Menu, X } from 'lucide-react';
import useRecentPatients from '../../hooks/useRecentPatients';

// Extract patient ID from any of the per-patient routes
function extractPatientId(pathname) {
  const m = pathname.match(/^\/(?:dashboard|patients|risk-analysis|case-comparison)\/(\d+)/);
  return m ? m[1] : null;
}

// Relative-time formatter (Korean)
function timeAgo(ts) {
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1) return '\uBC29\uAE08';
  if (m < 60) return `${m}\uBD84 \uC804`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}\uC2DC\uAC04 \uC804`;
  const d = Math.floor(h / 24);
  return `${d}\uC77C \uC804`;
}

export default function Sidebar() {
  const location = useLocation();
  const pid = extractPatientId(location.pathname);
  const recent = useRecentPatients();

  // F1: 모바일 토글 (lg 이하). lg 이상은 항상 펼침.
  const [mobileOpen, setMobileOpen] = useState(false);

  // 라우트 변경 시 모바일 메뉴 자동 닫기
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  // 모바일 오픈 시 Esc 로 닫기
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e) => { if (e.key === 'Escape') setMobileOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileOpen]);

  // disabled: 환자 컨텍스트가 필요한 메뉴. 환자 선택 전에는 클릭해도 이동하지 않고 툴팁만.
  const menuItems = [
    {
      key: 'home',
      to: '/home',
      label: 'Home',
      icon: Home,
      isActive: (p) => p === '/home' || p === '/',
    },
    {
      key: 'dashboard',
      to: pid ? `/dashboard/${pid}` : null,
      label: 'Dashboard',
      icon: LayoutDashboard,
      isActive: (p) => p === '/dashboard' || p.startsWith('/dashboard/'),
      disabledHint: '\uD658\uC790 \uC120\uD0DD \uD544\uC694',
    },
    {
      key: 'patients',
      to: '/patients', // 항상 리스트 페이지 (M2)
      label: 'Patient List',
      icon: Users,
      isActive: (p) => p === '/patients' || p.startsWith('/patients/'),
    },
    {
      key: 'risk',
      to: pid ? `/risk-analysis/${pid}` : null,
      label: 'Risk Analysis',
      icon: Activity,
      isActive: (p) => p.startsWith('/risk-analysis/'),
      disabledHint: '\uD658\uC790 \uC120\uD0DD \uD544\uC694',
    },
    {
      key: 'case',
      to: pid ? `/case-comparison/${pid}` : null,
      label: 'Case Comparison',
      icon: GitCompare,
      isActive: (p) => p.startsWith('/case-comparison/'),
      disabledHint: '\uD658\uC790 \uC120\uD0DD \uD544\uC694',
    },
    {
      key: 'settings',
      to: '/settings',
      label: 'Settings',
      icon: Settings,
      isActive: (p) => p === '/settings',
    },
  ];

  const triggerPalette = () => {
    window.dispatchEvent(new CustomEvent('dbcare:open-palette'));
  };

  return (
    <>
      {/* F1: 모바일 햄버거 트리거 (xl 이하에서만 노출) */}
      <button
        onClick={() => setMobileOpen((v) => !v)}
        aria-label={mobileOpen ? '\uBA54\uB274 \uB2EB\uAE30' : '\uBA54\uB274 \uC5F4\uAE30'}
        aria-expanded={mobileOpen}
        aria-controls="db-sidebar"
        className="xl:hidden fixed top-3 left-3 z-[60] p-2 rounded-lg bg-[#1e1e2e] text-white shadow-md hover:bg-[#2a2a3e] print:hidden"
      >
        {mobileOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
      </button>

      {/* F1: 모바일 backdrop (열렸을 때만) */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          className="xl:hidden fixed inset-0 z-40 bg-black/40 print:hidden"
          aria-hidden="true"
        />
      )}

    <aside
      id="db-sidebar"
      className={`fixed left-0 top-0 bottom-0 w-64 bg-[#1e1e2e] text-white flex flex-col z-50 print:hidden transition-transform duration-200 xl:translate-x-0 ${
        mobileOpen ? 'translate-x-0' : '-translate-x-full'
      }`}
    >
      {/* Logo */}
      <div className="px-6 py-5 border-b border-white/10">
        <h1 className="text-xl font-bold tracking-tight">
          <span className="text-accent">DB</span>-care
        </h1>
        <p className="text-[11px] text-gray-400 mt-0.5 tracking-wide">Diabetes Complication Predictor</p>
      </div>

      {/* Command palette trigger */}
      <button
        onClick={triggerPalette}
        className="mx-3 mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-left transition-colors group"
        title={'\uBAA8\uB4E0 \uD658\uC790 \uAC80\uC0C9 (Ctrl\u00B7K)'}
        aria-label="\ud658\uc790 \uac80\uc0c9 \uc5f4\uae30"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-400" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <span className="flex-1 text-[11px] text-gray-400 group-hover:text-gray-200 truncate">{'\uD658\uC790 \uAC80\uC0C9...'}</span>
        <span className="flex items-center gap-0.5 text-[9px] text-gray-500 font-mono" aria-hidden="true">
          <kbd className="px-1 py-0.5 rounded bg-white/10 border border-white/10">Ctrl</kbd>
          <kbd className="px-1 py-0.5 rounded bg-white/10 border border-white/10">K</kbd>
        </span>
      </button>

      {/* Menu */}
      <nav className="px-3 py-3 space-y-0.5" aria-label="\uc8fc \uba54\ub274">
        {menuItems.map(({ key, to, label, icon: Icon, isActive, disabledHint }) => {
          const active = isActive(location.pathname);
          const isDisabled = to === null;

          // 환자 선택 전: 클릭 비활성 + aria-disabled
          if (isDisabled) {
            return (
              <div
                key={key}
                role="link"
                aria-disabled="true"
                tabIndex={-1}
                title={disabledHint}
                className="group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-500 cursor-not-allowed opacity-60"
              >
                <Icon size={18} className="shrink-0" aria-hidden="true" />
                <span className="flex-1 truncate">{label}</span>
                <Lock size={11} className="shrink-0 text-gray-600" aria-hidden="true" />
              </div>
            );
          }

          return (
            <NavLink
              key={key}
              to={to}
              className={`group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-accent text-white shadow-sm'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Icon size={18} className="shrink-0" aria-hidden="true" />
              <span className="flex-1 truncate">{label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Recent patients */}
      {recent.length > 0 && (
        <div className="px-3 mt-1 flex-1 min-h-0 flex flex-col">
          <div className="px-3 mb-1.5 flex items-center gap-1.5">
            <Clock size={11} className="text-gray-500" aria-hidden="true" />
            <p className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold">{'\uCD5C\uADFC \uD658\uC790'}</p>
          </div>
          <div className="overflow-y-auto space-y-0.5 pb-2">
            {recent.map((p) => {
              const isCurrent = String(p.id) === pid;
              return (
                <Link
                  key={p.id}
                  to={`/dashboard/${p.id}`}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-colors ${
                    isCurrent ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center text-[10px] font-bold text-white shrink-0" aria-hidden="true">
                    {p.name?.[0] || '?'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{p.name}</p>
                    <p className="text-[9px] text-gray-500 truncate">
                      {p.chart_no} · {timeAgo(p.visitedAt)}
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {!recent.length && <div className="flex-1" />}

      {pid && (
        <div className="px-4 py-3 mx-3 mb-3 rounded-lg bg-white/5 border border-white/10">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{'\uD604\uC7AC \uD658\uC790 \uCEE8\uD14D\uC2A4\uD2B8'}</p>
          <p className="text-xs text-gray-200 font-medium">ID #{pid}</p>
        </div>
      )}

      <div className="px-6 py-4 border-t border-white/10 text-[11px] text-gray-500 leading-relaxed">
        {'\uBCD1\uC6D0 \uB0B4\uBD80\uC6A9 \uD504\uB85C\uADF8\uB7A8'}<br />
        © 2026 DB-care
      </div>
    </aside>
    </>
  );
}
