import { createContext, useContext, useState, useCallback, useRef } from 'react';
import ConfirmModal from '../components/ConfirmModal';

/**
 * 전역 confirm/alert 모달 컨텍스트.
 * window.confirm/alert 를 대체. promise 기반.
 *
 *   const confirm = useConfirm();
 *   const ok = await confirm({ title, message, tone:'danger', requireText:'DELETE' });
 *   if (!ok) return;
 */

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [state, setState] = useState({ open: false });
  const resolverRef = useRef(null);

  const confirm = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      // 이미 열려 있는 confirm 이 있으면 이전 resolver 를 false 로 종료
      //   (덮어쓰면 이전 await confirm(...) 이 영원히 pending 상태로 남음)
      resolverRef.current?.(false);
      resolverRef.current = resolve;
      setState({
        open: true,
        title: opts.title || '\uD655\uC778',
        message: opts.message || '',
        tone: opts.tone || 'default',
        confirmLabel: opts.confirmLabel || '\uD655\uC778',
        cancelLabel: opts.cancelLabel || '\uCDE8\uC18C',
        requireText: opts.requireText || null,
      });
    });
  }, []);

  const close = useCallback((result) => {
    resolverRef.current?.(result);
    resolverRef.current = null;
    setState({ open: false });
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <ConfirmModal
        open={state.open}
        title={state.title}
        message={state.message}
        tone={state.tone}
        confirmLabel={state.confirmLabel}
        cancelLabel={state.cancelLabel}
        requireText={state.requireText}
        onConfirm={() => close(true)}
        onCancel={() => close(false)}
      />
    </ConfirmContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider');
  return ctx;
}

export default ConfirmContext;
