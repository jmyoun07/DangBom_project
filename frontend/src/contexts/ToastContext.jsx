import { createContext, useContext, useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

const ToastContext = createContext(null);

let _id = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  // 자동 닫힘 타이머 추적 — unmount 시 일괄 정리 (setState-after-unmount 방지)
  const timersRef = useRef(new Map());

  const remove = useCallback((id) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((type, message, opts = {}) => {
    const id = ++_id;
    const duration = opts.duration ?? (type === 'error' ? 6000 : 3200);
    setToasts((list) => [...list, { id, type, message, title: opts.title }]);
    if (duration > 0) {
      timersRef.current.set(id, setTimeout(() => remove(id), duration));
    }
    return id;
  }, [remove]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach(clearTimeout);
      timers.clear();
    };
  }, []);

  // Provider value 안정화 — 렌더마다 새 객체가 내려가 소비자가 불필요하게 재렌더되는 것 방지
  const toast = useMemo(() => ({
    success: (msg, opts) => push('success', msg, opts),
    error: (msg, opts) => push('error', msg, opts),
    info: (msg, opts) => push('info', msg, opts),
    warn: (msg, opts) => push('warn', msg, opts),
    dismiss: remove,
  }), [push, remove]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="fixed top-20 right-6 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => {
          const cfg = TOAST_STYLE[t.type] || TOAST_STYLE.info;
          const Icon = cfg.Icon;
          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 min-w-[280px] max-w-md px-4 py-3 rounded-xl shadow-lg border ${cfg.bg} ${cfg.border} fade-in`}
            >
              <Icon size={18} className={cfg.icon} />
              <div className="flex-1 min-w-0">
                {t.title && <p className={`text-sm font-semibold ${cfg.title}`}>{t.title}</p>}
                <p className={`text-sm ${cfg.body} ${t.title ? 'mt-0.5' : ''}`}>{t.message}</p>
              </div>
              <button
                onClick={() => remove(t.id)}
                className="text-gray-400 hover:text-gray-700 transition-colors shrink-0"
                aria-label="close"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

const TOAST_STYLE = {
  success: {
    Icon: CheckCircle2,
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    icon: 'text-emerald-600',
    title: 'text-emerald-900',
    body: 'text-emerald-800',
  },
  error: {
    Icon: AlertCircle,
    bg: 'bg-red-50',
    border: 'border-red-200',
    icon: 'text-red-600',
    title: 'text-red-900',
    body: 'text-red-800',
  },
  warn: {
    Icon: AlertCircle,
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: 'text-amber-600',
    title: 'text-amber-900',
    body: 'text-amber-800',
  },
  info: {
    Icon: Info,
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    icon: 'text-blue-600',
    title: 'text-blue-900',
    body: 'text-blue-800',
  },
};
