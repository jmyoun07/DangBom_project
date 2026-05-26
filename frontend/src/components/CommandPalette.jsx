import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, User, LayoutDashboard, Activity, GitCompare, Upload, Users, Settings as SettingsIcon, Cog, Clock, CornerDownLeft } from 'lucide-react';
import api from '../api/client';
import useRecentPatients from '../hooks/useRecentPatients';

// Quick nav actions (always visible)
const NAV_ACTIONS = [
  { id: 'nav:home',       label: 'CSV \uC5C5\uB85C\uB4DC',          hint: '/home',       icon: Upload,          to: '/home' },
  { id: 'nav:dashboard',  label: '\uB300\uC2DC\uBCF4\uB4DC',        hint: '/dashboard',  icon: LayoutDashboard, to: '/dashboard' },
  { id: 'nav:patients',   label: '\uD658\uC790 \uBAA9\uB85D',       hint: '/patients',   icon: Users,           to: '/patients' },
  { id: 'nav:settings',   label: '\uC124\uC815',                    hint: '/settings',   icon: Cog,             to: '/settings' },
];

function highlight(text, q) {
  if (!q) return text;
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'i');
  const parts = String(text).split(re);
  return parts.map((p, i) =>
    i % 2 === 1 ? <mark key={i} className="bg-yellow-100 text-gray-900 rounded px-0.5">{p}</mark> : p
  );
}

export default function CommandPalette() {
  const navigate = useNavigate();
  const recent = useRecentPatients();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  // Open on Ctrl/Cmd+K, or on custom event
  useEffect(() => {
    const onKey = (e) => {
      const key = e.key?.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && key === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (key === 'escape' && open) {
        setOpen(false);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener('keydown', onKey);
    window.addEventListener('dbcare:open-palette', onOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('dbcare:open-palette', onOpen);
    };
  }, [open]);

  // Reset and focus on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [open]);

  // Debounced patient search
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (!q) { setResults([]); return; }
    setSearching(true);
    const h = setTimeout(async () => {
      try {
        const res = await api.get('/patients', { params: { page: 1, size: 10, search: q } });
        const items = res.data?.data?.items || res.data?.data || [];
        setResults(items);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 180);
    return () => clearTimeout(h);
  }, [query, open]);

  // Build the unified item list (for keyboard nav)
  const items = useMemo(() => {
    const q = query.trim();
    const list = [];
    if (q) {
      // Search results (patients)
      for (const p of results) {
        list.push({
          group: '\uD658\uC790 \uAC80\uC0C9 \uACB0\uACFC',
          type: 'patient',
          id: `p:${p.id}`,
          label: p.name,
          sub: `${p.chart_no} · ${p.sex === 'M' ? '\uB0A8' : '\uC5EC'} ${p.age}\uC138${p.phone ? ' · ' + p.phone : ''}`,
          avatar: p.name?.[0] || '?',
          onPick: () => navigate(`/dashboard/${p.id}`),
        });
      }
      // Nav actions (filtered by query)
      const filtered = NAV_ACTIONS.filter((a) => a.label.toLowerCase().includes(q.toLowerCase()));
      for (const a of filtered) {
        list.push({
          group: '\uD398\uC774\uC9C0 \uC774\uB3D9',
          type: 'nav',
          id: a.id,
          label: a.label,
          sub: a.hint,
          icon: a.icon,
          onPick: () => navigate(a.to),
        });
      }
    } else {
      // No query: show recent patients + quick nav
      for (const p of recent) {
        list.push({
          group: '\uCD5C\uADFC \uD658\uC790',
          type: 'recent',
          id: `r:${p.id}`,
          label: p.name,
          sub: `${p.chart_no} · ${p.sex === 'M' ? '\uB0A8' : '\uC5EC'} ${p.age}\uC138`,
          avatar: p.name?.[0] || '?',
          onPick: () => navigate(`/dashboard/${p.id}`),
        });
      }
      for (const a of NAV_ACTIONS) {
        list.push({
          group: '\uD398\uC774\uC9C0 \uC774\uB3D9',
          type: 'nav',
          id: a.id,
          label: a.label,
          sub: a.hint,
          icon: a.icon,
          onPick: () => navigate(a.to),
        });
      }
    }
    return list;
  }, [query, results, recent, navigate]);

  // Reset active index when list changes
  useEffect(() => { setActive(0); }, [query, results.length]);

  // Keyboard nav inside the palette
  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, items.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      const it = items[active];
      if (it) { it.onPick(); setOpen(false); }
    }
  };

  if (!open) return null;

  // Group items for rendering
  const grouped = [];
  let curGroup = null;
  items.forEach((it, idx) => {
    if (it.group !== curGroup) {
      grouped.push({ type: 'header', label: it.group });
      curGroup = it.group;
    }
    grouped.push({ type: 'item', it, idx });
  });

  const activeItem = items[active];
  const activeId = activeItem ? `palette-item-${activeItem.id}` : undefined;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center pt-[15vh] px-4 bg-black/40 backdrop-blur-sm fade-in"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={'\uBA85\uB839 \uD314\uB808\uD2B8 \u2014 \uD658\uC790 \uAC80\uC0C9 \uBC0F \uD398\uC774\uC9C0 \uC774\uB3D9'}
        className="w-full max-w-xl bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
          <Search size={16} className="text-gray-400 shrink-0" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-listbox"
            aria-autocomplete="list"
            aria-activedescendant={activeId}
            aria-label={'\uD658\uC790 \uAC80\uC0C9 \uBC0F \uD398\uC774\uC9C0 \uC774\uB3D9'}
            placeholder={'\uD658\uC790 \uC774\uB984 \u00B7 \uCC28\uD2B8\uBC88\uD638 \u00B7 \uC5F0\uB77D\uCC98 \uAC80\uC0C9 \uB610\uB294 \uD398\uC774\uC9C0 \uC774\uB3D9...'}
            className="flex-1 bg-transparent outline-none text-sm text-gray-900 placeholder:text-gray-400"
          />
          {searching && (
            <div
              className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent"
              role="status"
              aria-label={'\uAC80\uC0C9 \uC911'}
            />
          )}
          <kbd className="hidden md:inline text-[10px] text-gray-400 border border-gray-200 rounded px-1.5 py-0.5 font-mono">Esc</kbd>
        </div>

        {/* aria-live: 결과 수 변동 안내 (스크린리더용 비가시) */}
        <span className="sr-only" aria-live="polite">
          {items.length === 0
            ? (query ? '\uAC80\uC0C9 \uACB0\uACFC \uC5C6\uC74C' : '')
            : `${items.length}\uAC1C \uACB0\uACFC`}
        </span>

        {/* Results */}
        <div
          id="palette-listbox"
          role="listbox"
          aria-label={'\uAC80\uC0C9 \uACB0\uACFC'}
          className="max-h-[50vh] overflow-y-auto py-2"
          onKeyDown={onKeyDown}
        >
          {items.length === 0 && (
            <div className="px-4 py-10 text-center">
              <p className="text-sm text-gray-500">
                {query ? '\uAC80\uC0C9 \uACB0\uACFC\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4' : '\uCD5C\uADFC \uD658\uC790\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4'}
              </p>
              {!query && (
                <p className="text-[11px] text-gray-400 mt-1">
                  {'\uD658\uC790 \uC774\uB984\uC774\uB098 \uCC28\uD2B8\uBC88\uD638\uB97C \uC785\uB825\uD574\uBCF4\uC138\uC694'}
                </p>
              )}
            </div>
          )}

          {grouped.map((row, i) => {
            if (row.type === 'header') {
              return (
                <p
                  key={`h-${i}`}
                  role="presentation"
                  className="px-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400"
                >
                  {row.label}
                </p>
              );
            }
            const { it, idx } = row;
            const isActive = idx === active;
            const Icon = it.icon;
            return (
              <button
                key={it.id}
                id={`palette-item-${it.id}`}
                role="option"
                aria-selected={isActive}
                onMouseEnter={() => setActive(idx)}
                onClick={() => { it.onPick(); setOpen(false); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                  isActive ? 'bg-accent-soft' : 'hover:bg-gray-50'
                }`}
              >
                {it.avatar ? (
                  <div
                    aria-hidden="true"
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                      isActive ? 'bg-accent text-white' : 'bg-gray-800 text-white'
                    }`}
                  >
                    {it.avatar}
                  </div>
                ) : Icon ? (
                  <div
                    aria-hidden="true"
                    className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                      isActive ? 'bg-accent text-white' : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    <Icon size={14} />
                  </div>
                ) : null}
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium truncate ${isActive ? 'text-accent' : 'text-gray-900'}`}>
                    {highlight(it.label, query.trim())}
                  </p>
                  <p className="text-[11px] text-gray-500 truncate">{it.sub}</p>
                </div>
                {isActive && <CornerDownLeft size={14} className="text-accent shrink-0" aria-hidden="true" />}
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-gray-100 bg-gray-50 flex items-center justify-between text-[10px] text-gray-500">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-white border border-gray-200 rounded font-mono">↑↓</kbd> {'\uC774\uB3D9'}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-white border border-gray-200 rounded font-mono">Enter</kbd> {'\uC120\uD0DD'}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-white border border-gray-200 rounded font-mono">Esc</kbd> {'\uB2EB\uAE30'}
            </span>
          </div>
          <span className="text-gray-400">DB-care</span>
        </div>
      </div>
    </div>
  );
}
