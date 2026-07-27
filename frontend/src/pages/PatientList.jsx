import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Search, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ChevronsUpDown, SlidersHorizontal, Phone, X, LayoutDashboard, Activity, GitCompare, Trash2 } from 'lucide-react';
import api, { errorMessage } from '../api/client';
import RiskBadge from '../components/RiskBadge';
import EmptyState from '../components/EmptyState';
import usePatientCount from '../hooks/usePatientCount';
import { removeRecentPatient } from '../hooks/useRecentPatients';
import { invalidatePatientContextCache } from '../components/layout/PatientContextBar';
import { prodSafeError } from '../theme';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../contexts/ConfirmContext';

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

// 위험도 정렬 가중치 (고>중>저). 모듈 레벨 상수 → 안정 참조(useMemo deps 불필요).
const RISK_ORDER = { '고위험': 3, '중위험': 2, '저위험': 1 };

const readPageParam = (params) => {
  const n = parseInt(params.get('page') || '1', 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
};

// 항목4: 클릭 정렬 가능한 테이블 헤더 셀.
function SortableTh({ label, sortKey, sortBy, sortOrder, onSort }) {
  const active = sortBy === sortKey;
  const Icon = !active ? ChevronsUpDown : sortOrder === 'asc' ? ChevronUp : ChevronDown;
  return (
    <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={`inline-flex items-center gap-1 uppercase tracking-wider hover:text-accent transition-colors ${active ? 'text-accent' : ''}`}
      >
        {label}
        <Icon size={12} className={active ? 'text-accent' : 'text-gray-300'} />
      </button>
    </th>
  );
}

export default function PatientList() {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const { count, loading: countLoading, error: countError, refetch: refetchCount } = usePatientCount();
  const [patients, setPatients] = useState([]);
  const [total, setTotal] = useState(0);
  // v2.1.2 — page/search/risk_level 을 URL search param 으로 동기화.
  // 환자 카드 클릭 → 대시보드 → 뒤로가기 시 마지막 페이지로 복원되도록.
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPageState] = useState(() => readPageParam(searchParams));
  const [size] = useState(8);
  const [search, setSearchState] = useState(() => searchParams.get('search') || '');
  const [riskLevel, setRiskLevelState] = useState(() => searchParams.get('risk') || '');

  // 상태 변경 시 URL 도 함께 갱신 (replace 가 아니라 push — back 으로 복원 가능).
  // pageRef 로 최신 page 추적 → functional setPage 의 stale closure 방지.
  const pageRef = useRef(page);
  useEffect(() => { pageRef.current = page; }, [page]);
  const setPage = useCallback((next, { replace = false } = {}) => {
    const v = Math.max(1, typeof next === 'function' ? next(pageRef.current) : next);
    pageRef.current = v;
    setPageState(v);
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      if (v <= 1) sp.delete('page'); else sp.set('page', String(v));
      return sp;
    }, { replace });
  }, [setSearchParams]);
  // v2.2.9 (#7): functional setSearchParams + useCallback 으로 안정 참조화.
  //   (렌더마다 재생성되며 searchParams 스냅샷을 캡처하면 키보드 단축키 effect 가 stale closure 로 동작)
  const setSearch = useCallback((v) => {
    setSearchState(v);
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      if (!v) sp.delete('search'); else sp.set('search', v);
      sp.delete('page');
      return sp;
    }, { replace: false });
  }, [setSearchParams]);
  const setRiskLevel = (v) => {
    setRiskLevelState(v);
    const sp = new URLSearchParams(searchParams);
    if (!v) sp.delete('risk'); else sp.set('risk', v);
    sp.delete('page');
    setSearchParams(sp, { replace: false });
  };
  // 항목4: 정렬 상태 (URL 동기화 → 뒤로가기 시 정렬도 복원).
  const [sortBy, setSortByState] = useState(() => searchParams.get('sort') || '');
  const [sortOrder, setSortOrderState] = useState(() => searchParams.get('order') || 'asc');
  const setSort = (key) => {
    let nextBy = key, nextOrder = 'asc';
    if (sortBy === key) {
      if (sortOrder === 'asc') nextOrder = 'desc';
      else { nextBy = ''; nextOrder = 'asc'; }  // 3번째 클릭 → 정렬 해제
    }
    setSortByState(nextBy);
    setSortOrderState(nextOrder);
    const sp = new URLSearchParams(searchParams);
    if (!nextBy) { sp.delete('sort'); sp.delete('order'); }
    else { sp.set('sort', nextBy); sp.set('order', nextOrder); }
    setSearchParams(sp, { replace: false });
  };

  // URL(searchParams) → state 재동기화: 브라우저 뒤로/앞으로 시 page·검색·정렬 복원.
  //   (3페이지에서 상세 진입 후 뒤로가기 → 3페이지로 복원)
  useEffect(() => {
    setPageState(readPageParam(searchParams));
    setSearchState(searchParams.get('search') || '');
    setRiskLevelState(searchParams.get('risk') || '');
    setSortByState(searchParams.get('sort') || '');
    setSortOrderState(searchParams.get('order') || 'asc');
  }, [searchParams]);
  const [loading, setLoading] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filters, setFilters] = useState(initialFilters);
  const searchRef = useRef(null);
  const [refreshTick, setRefreshTick] = useState(0);

  // 개별 환자 삭제 — 확인 후 DELETE /patients/{id} (검사이력·감사로그 함께 삭제됨).
  const handleDelete = async (p, e) => {
    e?.stopPropagation();
    const ok = await confirm({
      title: '환자 삭제',
      message: `'${p.name}' (${p.chart_no}) 환자의 모든 데이터(검사 이력 포함)를 삭제합니다.\n되돌릴 수 없습니다.`,
      tone: 'danger',
      confirmLabel: '삭제',
      cancelLabel: '취소',
    });
    if (!ok) return;
    try {
      await api.delete(`/patients/${p.id}`);
      setPatients((list) => list.filter((x) => x.id !== p.id));  // 목록에서 즉시 제거
      // 삭제된 환자의 잔존 흔적 정리: 최근 환자 목록 + PatientContextBar 캐시
      //   (캐시는 notify:false — 삭제된 환자를 다시 GET 해서 404 나는 것 방지)
      removeRecentPatient(p.id);
      invalidatePatientContextCache(p.id, { notify: false });
      toast.success(`'${p.name}' 환자가 삭제되었습니다.`, { title: '삭제 완료' });
      setRefreshTick((t) => t + 1);  // 목록 서버 재조회
      refetchCount();                // 전체 환자 수 갱신 (마지막 환자 삭제 시 빈 상태 반영)
    } catch (err) {
      prodSafeError('PatientList.delete')(err);
      toast.error(errorMessage(err, '삭제 중 오류가 발생했습니다. 다시 시도해주세요.'), { title: '삭제 실패' });
    }
  };

  useEffect(() => {
    if (countLoading || count === 0) return;
    const t = setTimeout(() => {
      const fetch = async () => {
        setLoading(true);
        try {
          // Backend doesn't support advanced filters yet; fetch the full set and post-filter/paginate client-side.
          // v2.2.8: size 를 전체 환자 수에 맞춰 조회 → 1706명 중 100명만 보이던 문제 + total 오류 해소.
          //   (장기적으로는 정렬/고급필터까지 서버사이드 페이징으로 옮기는 것이 정석)
          // v2.3.6: 상한 5000 이면 환자가 그 이상일 때 서버가 422 로 거부해 목록이 통째로 실패했다.
          //   백엔드 상한(50000)과 맞춰 병원 규모가 커져도 목록이 끊기지 않게 한다.
          const params = { page: 1, size: Math.min(Math.max(count || 200, 200), 50000) };
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
  }, [search, riskLevel, count, countLoading, refreshTick]);

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

  // 항목4: 정렬 (필터 후, 페이지 슬라이스 전). 위험도는 의미순(고>중>저, RISK_ORDER 모듈 상수).
  const sorted = useMemo(() => {
    if (!sortBy) return filtered;
    const dir = sortOrder === 'desc' ? -1 : 1;
    const arr = [...filtered];
    arr.sort((a, b) => {
      switch (sortBy) {
        case 'name': return dir * (a.name || '').localeCompare(b.name || '', 'ko-KR');
        case 'chart_no': return dir * (a.chart_no || '').localeCompare(b.chart_no || '', 'ko-KR');
        case 'sex': return dir * (a.sex || '').localeCompare(b.sex || '');
        case 'age': return dir * ((a.age ?? -Infinity) - (b.age ?? -Infinity));
        case 'exam_date': return dir * (new Date(a.exam_date || a.upload_date || 0) - new Date(b.exam_date || b.upload_date || 0));
        case 'risk_level': return dir * ((RISK_ORDER[a.risk_level] || 0) - (RISK_ORDER[b.risk_level] || 0));
        default: return 0;
      }
    });
    return arr;
  }, [filtered, sortBy, sortOrder]);

  // 고급 필터(성별/나이/검사일 — 로컬 상태, URL 미반영)가 바뀌면 1페이지로 리셋.
  //   검색/위험도는 setSearch/setRiskLevel 이 URL 의 page 를 지우고 위 재동기화 effect 가
  //   page=1 로 복원하므로 여기서 제외 (재동기화와 중복/충돌 방지 → 뒤로가기 복원 안정).
  const filtersSig = JSON.stringify(filters);
  const prevFiltersRef = useRef(filtersSig);
  useEffect(() => { setTotal(filtered.length); }, [filtered.length]);
  useEffect(() => {
    if (prevFiltersRef.current !== filtersSig) {
      prevFiltersRef.current = filtersSig;
      setPage(1);
    }
  }, [filtersSig]);  // eslint-disable-line react-hooks/exhaustive-deps
  // 복원된 page 가 데이터 범위를 벗어나면(로드 완료 후) 클램프 (history 오염 방지 위해 replace).
  useEffect(() => {
    const tp = Math.ceil(filtered.length / size) || 1;
    if (!loading && page > tp) setPage(tp, { replace: true });
  }, [loading, filtered.length, page, size]);  // eslint-disable-line react-hooks/exhaustive-deps

  const visible = sorted.slice((page - 1) * size, page * size);
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
      // v2.2.9 (#24): 모달(Confirm/편집 등)이 열려 있으면 목록 단축키 무시 (모달 조작과 충돌 방지)
      if (document.querySelector('[role="dialog"]')) return;
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
    // setPage/setSearch 는 useCallback 안정 참조 (deps 포함해도 재구독 없음).
  }, [totalPages, setPage, setSearch]);

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

  // v2.2.9 (#7): \uC11C\uBC84 \uC5F0\uACB0 \uC624\uB958\uB97C '\uD658\uC790 \uC5C6\uC74C'\uACFC \uAD6C\uBD84\uD574 \uD45C\uC2DC (\uC7AC\uC5C5\uB85C\uB4DC \uC624\uC778 \uBC29\uC9C0).
  if (!countLoading && countError) {
    return (
      <EmptyState
        title={'\uC11C\uBC84\uC5D0 \uC5F0\uACB0\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4'}
        message={'\uBC31\uC5D4\uB4DC \uC751\uB2F5\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uB370\uC774\uD130\uAC00 \uC0AC\uB77C\uC9C4 \uAC83\uC774 \uC544\uB2C8\uBA70, \uC7A0\uC2DC \uD6C4 \uC0C8\uB85C\uACE0\uCE68\uD574 \uC8FC\uC138\uC694.'}
      />
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
              onChange={(e) => setSearch(e.target.value)}
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
            onChange={(e) => setRiskLevel(e.target.value)}
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
              <SortableTh label={'\uC774\uB984'} sortKey="name" sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} />
              <SortableTh label={'\uCC28\uD2B8\uBC88\uD638'} sortKey="chart_no" sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} />
              <SortableTh label={'\uB098\uC774'} sortKey="age" sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} />
              <SortableTh label={'\uC131\uBCC4'} sortKey="sex" sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} />
              <th className="text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-3">{'\uC5F0\uB77D\uCC98'}</th>
              <SortableTh label={'\uCD5C\uADFC \uAC80\uC0AC\uC77C'} sortKey="exam_date" sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} />
              <SortableTh label={'\uC704\uD5D8\uB3C4'} sortKey="risk_level" sortBy={sortBy} sortOrder={sortOrder} onSort={setSort} />
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
                        <button
                          type="button"
                          onClick={(e) => handleDelete(p, e)}
                          title="환자 삭제"
                          className="p-1.5 rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
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
