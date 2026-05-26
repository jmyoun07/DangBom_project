import { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Search, ChevronLeft, ChevronRight, SlidersHorizontal, Phone, X, LayoutDashboard, Activity, GitCompare } from 'lucide-react';
import api from '../api/client';
import RiskBadge from '../components/RiskBadge';
import EmptyState from '../components/EmptyState';
import usePatientCount from '../hooks/usePatientCount';
import { prodSafeError } from '../theme';

/**
 * 동적 페이지 윈도우 — 현재 페이지 주변 5개만 표시, 앞뒤는 "..." 처리.
 * 예) totalPages=12, page=7 → [1, ..., 5, 6, 7, 8, 9, ..., 12]
 */
function paginationWindow(page, totalPages, windowSize = 5) {
  if (totalPages <= windowSize + 2) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const half = Math.floor(windowSize / 2);
  let start = Math.max(2, page - half);
  let end = Math.min(totalPages - 1, page + half);
  if (page <= half + 1) end = windowSize;
  if (page >= totalPages - half) start = totalPages - windowSize + 1;
  const pages = [1];
  if (start > 2) pages.push('...L');
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < totalPages - 1) pages.push('...R');
  pages.push(totalPages);
  return pages;
}

const initialFilters = { sex: '', examFrom: '', examTo: '', minAge: '', maxAge: '' };

export default function PatientList() {
  const navigate = useNavigate();
  const { count, loading: countLoading } = usePatientCount();
  const [patients, setPatients] = useState([]);
  const [total, setTotal] = useState(0);
  // v2.1.2 — page/search/risk_level 을 URL search param 으로 동기화.
  // 환자 카드 클릭 → 대시보드 → 뒤로가기 시 마지막 페이지로 복원되도록.
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPageState] = useState(() => parseInt(searchParams.get('page') || '1', 10) || 1);
  const [size] = useState(8);
  const [search, setSearchState] = useState(() => searchParams.get('search') || '');
  const [riskLevel, setRiskLevelState] = useState(() => searchParams.get('risk') || '');

  // 상태 변경 시 URL 도 함께 갱신 (replace 가 아니라 push — back 으로 복원 가능)
  const setPage = (next) => {
    const v = typeof next === 'function' ? next(page) : next;
    setPageState(v);
    const sp = new URLSearchParams(searchParams);
    if (v <= 1) sp.delete('page'); else sp.set('page', String(v));
    setSearchParams(sp, { replace: false });
  };
  const setSearch = (v) => {
    setSearchState(v);
    const sp = new URLSearchParams(searchParams);
    if (!v) sp.delete('search'); else sp.set('search', v);
    sp.delete('page');
    setSearchParams(sp, { replace: false });
  };
  const setRiskLevel = (v) => {
    setRiskLevelState(v);
    const sp = new URLSearchParams(searchParams);
    if (!v) sp.delete('risk'); else sp.set('risk', v);
    sp.delete('page');
    setSearchParams(sp, { replace: false });
  };
  const [loading, setLoading] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filters, setFilters] = useState(initialFilters);
  const searchRef = useRef(null);

  useEffect(() => {
    if (countLoading || count === 0) return;
    const t = setTimeout(() => {
      const fetch = async () => {
        setLoading(true);
        try {
          // Backend doesn't support advanced filters yet; fetch a wider page and post-filter client-side.
          const params = { page: 1, size: 100 };
          if (search) params.search = search;
          if (riskLevel) params.risk_level = riskLevel;
          const res = await api.get('/patients', { params });
          setPatients(res.data.data || []);
        } catch (e) {
          prodSafeError('PatientList.fetch')(e);
        } finally {
          setLoading(false);
        }
      };
      fetch();
    }, 250);
    return () => clearTimeout(t);
  }, [search, riskLevel, count, countLoading]);

  // Client-side advanced filtering
  const filtered = useMemo(() => {
    return patients.filter((p) => {
      if (filters.sex && p.sex !== filters.sex) return false;
      if (filters.minAge && p.age != null && p.age < Number(filters.minAge)) return false;
      if (filters.maxAge && p.age != null && p.age > Number(filters.maxAge)) return false;
      const exam = p.exam_date || p.upload_date;
      if (exam && filters.examFrom && new Date(exam) < new Date(filters.examFrom)) return false;
      if (exam && filters.examTo && new Date(exam) > new Date(filters.examTo)) return false;
      return true;
    });
  }, [patients, filters]);

  // Update total + slice for current page
  useEffect(() => { setTotal(filtered.length); setPage(1); }, [filtered.length]);
  const visible = filtered.slice((page - 1) * size, page * size);
  const totalPages = Math.ceil(total / size) || 1;
  const startIdx = total === 0 ? 0 : (page - 1) * size + 1;
  const endIdx = Math.min(page * size, total);

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  // Keyboard shortcuts: ←/→ pagination, / to focus search, Esc to clear search
  useEffect(() => {
    const onKey = (e) => {
      // Ignore when typing in any input/select/textarea or when palette/modal might be open
      const tag = (e.target?.tagName || '').toUpperCase();
      const typing = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || e.target?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') return; // palette owns this
      if (e.key === '/' && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === 'Escape' && document.activeElement === searchRef.current) {
        setSearch('');
      } else if (e.key === 'ArrowLeft' && !typing) {
        setPage((p) => Math.max(1, p - 1));
      } else if (e.key === 'ArrowRight' && !typing) {
        setPage((p) => Math.min(totalPages, p + 1));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [totalPages]);

  const formatPhone = (raw) => {
    if (!raw) return '\u2014';
    const digits = String(raw).replace(/\D/g, '');
    if (digits.length === 11) return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
    if (digits.length === 10) return `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`;
    return raw;
  };

  if (countLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" style={{ borderBottomColor: 'var(--db-accent)' }} />
      </div>
    );
  }

  if (count === 0) {
    return (
      <EmptyState
        title={'\uB4F1\uB85D\uB41C \uD658\uC790\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4'}
        message={'CSV \uD30C\uC77C\uC744 \uC5C5\uB85C\uB4DC\uD574 \uD658\uC790 \uB370\uC774\uD130\uB97C \uB4F1\uB85D\uD558\uBA74 \uC774 \uD654\uBA74\uC5D0\uC11C \uBAA9\uB85D\uC744 \uD655\uC778\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.'}
      />
    );
  }

  return (
    <div className="space-y-5 fade-in w-full">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{'\uD658\uC790 \uBAA9\uB85D \uAD00\uB9AC'}</h1>
        <p className="text-sm text-gray-500 mt-1">{'\uB4F1\uB85D\uB41C \uD658\uC790\uB4E4\uC744 \uC870\uD68C\uD558\uACE0 \uAD00\uB9AC\uD569\uB2C8\uB2E4.'}</p>
      </div>

      {/* Search & Filter */}
      <div className="card-elevated p-4 space-y-3">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              ref={searchRef}
              type="text"
              placeholder={'\uC774\uB984, \uCC28\uD2B8\uBC88\uD638 \uB610\uB294 \uC5F0\uB77D\uCC98\uB85C \uAC80\uC0C9... ( / \uD0A4\uB85C \uD3EC\uCEE4\uC2A4)'}
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="w-full pl-9 pr-9 py-2 border border-gray-200 rounded-lg text-sm accent-input"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-700 rounded"
                aria-label="clear"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <select
            value={riskLevel}
            onChange={(e) => { setRiskLevel(e.target.value); setPage(1); }}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm accent-input"
          >
            <option value="">{'\uC804\uCCB4 \uC704\uD5D8\uB3C4'}</option>
            <option value={'\uC800\uC704\uD5D8'}>{'\uC800\uC704\uD5D8'}</option>
            <option value={'\uC911\uC704\uD5D8'}>{'\uC911\uC704\uD5D8'}</option>
            <option value={'\uACE0\uC704\uD5D8'}>{'\uACE0\uC704\uD5D8'}</option>
          </select>
          <button
            onClick={() => setFilterOpen((v) => !v)}
            className={`relative flex items-center gap-1.5 px-3 py-2 border rounded-lg text-sm transition-colors ${
              filterOpen || activeFilterCount > 0
                ? 'bg-accent-soft border-accent text-accent'
                : 'border-gray-200 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <SlidersHorizontal size={14} />
            {'\uD544\uD130'}
            {activeFilterCount > 0 && (
              <span className="ml-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] text-[10px] font-bold rounded-full bg-accent text-white px-1">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {filterOpen && (
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 grid grid-cols-4 gap-3 fade-in">
            <label className="flex flex-col text-xs text-gray-600">
              <span className="font-medium mb-1">{'\uC131\uBCC4'}</span>
              <select
                value={filters.sex}
                onChange={(e) => setFilters((f) => ({ ...f, sex: e.target.value }))}
                className="px-2 py-1.5 border border-gray-200 rounded-md text-xs bg-white accent-input"
              >
                <option value="">{'\uC804\uCCB4'}</option>
                <option value="M">{'\uB0A8\uC131'}</option>
                <option value="F">{'\uC5EC\uC131'}</option>
              </select>
            </label>
            <label className="flex flex-col text-xs text-gray-600">
              <span className="font-medium mb-1">{'\uAC80\uC0AC\uC77C \uC2DC\uC791'}</span>
              <input
                type="date"
                value={filters.examFrom}
                onChange={(e) => setFilters((f) => ({ ...f, examFrom: e.target.value }))}
                className="px-2 py-1.5 border border-gray-200 rounded-md text-xs bg-white accent-input"
              />
            </label>
            <label className="flex flex-col text-xs text-gray-600">
              <span className="font-medium mb-1">{'\uAC80\uC0AC\uC77C \uC885\uB8CC'}</span>
              <input
                type="date"
                value={filters.examTo}
                onChange={(e) => setFilters((f) => ({ ...f, examTo: e.target.value }))}
                className="px-2 py-1.5 border border-gray-200 rounded-md text-xs bg-white accent-input"
              />
            </label>
            <div className="flex flex-col text-xs text-gray-600">
              <span className="font-medium mb-1">{'\uB098\uC774 \uBC94\uC704'}</span>
              <div className="flex items-center gap-1">
                <input
                  type="number" min="0" max="120" placeholder="0"
                  value={filters.minAge}
                  onChange={(e) => setFilters((f) => ({ ...f, minAge: e.target.value }))}
                  className="w-full px-2 py-1.5 border border-gray-200 rounded-md text-xs bg-white accent-input"
                />
                <span className="text-gray-400">~</span>
                <input
                  type="number" min="0" max="120" placeholder="120"
                  value={filters.maxAge}
                  onChange={(e) => setFilters((f) => ({ ...f, maxAge: e.target.value }))}
                  className="w-full px-2 py-1.5 border border-gray-200 rounded-md text-xs bg-white accent-input"
                />
              </div>
            </div>
            <div className="col-span-4 flex justify-end gap-2 pt-1">
              <button
                onClick={() => setFilters(initialFilters)}
                className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-700 px-2 py-1 rounded-md hover:bg-gray-100"
              >
                <X size={12} /> {'\uD544\uD130 \uCD08\uAE30\uD654'}
              </button>
              <button
                onClick={() => setFilterOpen(false)}
                className="text-[11px] font-semibold text-white bg-accent hover:bg-accent-dark px-3 py-1.5 rounded-md transition-colors"
              >
                {'\uC801\uC6A9 \uC644\uB8CC'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="card-elevated overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50/80 border-b border-gray-100">
            <tr>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uC774\uB984'}</th>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uCC28\uD2B8\uBC88\uD638'}</th>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uB098\uC774'}</th>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uC131\uBCC4'}</th>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uC5F0\uB77D\uCC98'}</th>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uCD5C\uADFC \uAC80\uC0AC\uC77C'}</th>
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uC704\uD5D8\uB3C4'}</th>
              <th className="text-right text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uAD00\uB9AC'}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={`sk-${i}`} className="animate-pulse">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-gray-100" />
                      <div className="h-3 w-20 bg-gray-100 rounded" />
                    </div>
                  </td>
                  <td className="px-5 py-3"><div className="h-3 w-24 bg-gray-100 rounded" /></td>
                  <td className="px-5 py-3"><div className="h-3 w-10 bg-gray-100 rounded" /></td>
                  <td className="px-5 py-3"><div className="h-3 w-6 bg-gray-100 rounded" /></td>
                  <td className="px-5 py-3"><div className="h-3 w-28 bg-gray-100 rounded" /></td>
                  <td className="px-5 py-3"><div className="h-3 w-20 bg-gray-100 rounded" /></td>
                  <td className="px-5 py-3"><div className="h-5 w-14 bg-gray-100 rounded-full" /></td>
                  <td className="px-5 py-3"><div className="h-6 w-20 bg-gray-100 rounded ml-auto" /></td>
                </tr>
              ))
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan="8" className="text-center py-12 text-gray-400 text-sm">{'\uAC80\uC0C9 \uACB0\uACFC\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.'}</td>
              </tr>
            ) : (
              visible.map((p) => {
                const examDate = p.exam_date || p.upload_date;
                const onRowClick = () => navigate(`/dashboard/${p.id}`);
                const stop = (e) => e.stopPropagation();
                return (
                  <tr
                    key={p.id}
                    onClick={onRowClick}
                    className="hover:bg-accent-soft/60 transition-colors cursor-pointer group"
                    title={'\uB300\uC2DC\uBCF4\uB4DC \uC5F4\uAE30'}
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-xs font-bold shadow-sm">
                          {(p.name || '?')[0]}
                        </div>
                        <span className="text-sm font-medium text-gray-800 group-hover:text-accent transition-colors">{p.name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600 font-mono tracking-tight">{p.chart_no}</td>
                    <td className="px-5 py-3 text-sm text-gray-600 tabular-nums">{p.age ? `${p.age}\uC138` : '\u2014'}</td>
                    <td className="px-5 py-3 text-sm text-gray-600">{p.sex === 'M' ? '\uB0A8' : p.sex === 'F' ? '\uC5EC' : '\u2014'}</td>
                    <td className="px-5 py-3 text-sm text-gray-600 font-mono">
                      <span className="flex items-center gap-1.5">
                        <Phone size={12} className="text-gray-400" />
                        {formatPhone(p.phone)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600 tabular-nums">
                      {examDate ? new Date(examDate).toLocaleDateString('ko-KR') : '\u2014'}
                    </td>
                    <td className="px-5 py-3"><RiskBadge level={p.risk_level} /></td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-1" onClick={stop}>
                        <Link
                          to={`/dashboard/${p.id}`}
                          title={'\uB300\uC2DC\uBCF4\uB4DC'}
                          className="p-1.5 rounded-md text-gray-500 hover:bg-accent-soft hover:text-accent transition-colors"
                        >
                          <LayoutDashboard size={14} />
                        </Link>
                        <Link
                          to={`/risk-analysis/${p.id}`}
                          title={'\uC2DC\uB098\uB9AC\uC624 \uBD84\uC11D'}
                          className="p-1.5 rounded-md text-gray-500 hover:bg-accent-soft hover:text-accent transition-colors"
                        >
                          <Activity size={14} />
                        </Link>
                        <Link
                          to={`/case-comparison/${p.id}`}
                          title={'\uC720\uC0AC \uC0AC\uB840'}
                          className="p-1.5 rounded-md text-gray-500 hover:bg-accent-soft hover:text-accent transition-colors"
                        >
                          <GitCompare size={14} />
                        </Link>
                        <Link
                          to={`/patients/${p.id}`}
                          className="ml-1 text-xs text-accent font-medium hover:underline whitespace-nowrap"
                        >
                          {'\uC0C1\uC138'} &rsaquo;
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <p className="text-sm text-gray-500">
            {'\uC804\uCCB4'} <span className="font-semibold text-gray-700">{total}</span>{'\uBA85 \uC911'} {startIdx}-{endIdx} {'\uD45C\uC2DC \uC911'}
          </p>
          {/* D9: 단축키 힌트 — sm+ 에서 화살표/검색 모두, 모바일은 / 만 노출 (공간 협소) */}
          <span className="flex items-center gap-2 text-[10px] text-gray-400" aria-label="\ud0a4\ubcf4\ub4dc \ub2e8\ucd95\ud0a4 \uc548\ub0b4">
            <span className="hidden sm:flex items-center gap-0.5">
              <kbd className="px-1 py-0.5 bg-white border border-gray-200 rounded font-mono">←</kbd>
              <kbd className="px-1 py-0.5 bg-white border border-gray-200 rounded font-mono">→</kbd> {'\uD398\uC774\uC9C0'}
            </span>
            <span className="flex items-center gap-0.5">
              <kbd className="px-1 py-0.5 bg-white border border-gray-200 rounded font-mono">/</kbd> {'\uAC80\uC0C9'}
            </span>
          </span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
          >
            <ChevronLeft size={14} />
          </button>
          {paginationWindow(page, totalPages).map((n, i) => {
            if (n === '...L' || n === '...R') {
              return (
                <span
                  key={`${n}-${i}`}
                  aria-hidden="true"
                  className="px-2 py-1.5 text-sm text-gray-400 select-none"
                >
                  {'\u2026'}
                </span>
              );
            }
            const isCurrent = page === n;
            return (
              <button
                key={n}
                onClick={() => setPage(n)}
                aria-current={isCurrent ? 'page' : undefined}
                aria-label={`${n}\uD398\uC774\uC9C0\uB85C \uC774\uB3D9`}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors tabular-nums ${
                  isCurrent ? 'bg-accent text-white' : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                {n}
              </button>
            );
          })}
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
