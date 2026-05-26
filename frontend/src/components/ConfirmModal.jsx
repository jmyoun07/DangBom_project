import { useEffect, useRef, useState, useCallback } from 'react';
import { AlertTriangle, X, Info } from 'lucide-react';

/**
 * 커스텀 confirm/alert 모달.
 * - role="dialog" + aria-modal + aria-labelledby/aria-describedby (D2)
 * - 포커스 트랩 (Tab/Shift+Tab) + Esc 닫기 + 첫 진입 시 취소 버튼에 포커스
 * - tone="danger" 일 경우 추가 텍스트 입력으로 2차 확인 (J4)
 *
 * 사용:
 *   const confirm = useConfirm();
 *   const ok = await confirm({ title, message, tone, requireText, confirmLabel });
 */

function FocusTrapModal({
  open,
  title,
  message,
  tone = 'default',
  confirmLabel,
  cancelLabel,
  requireText,
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const inputRef = useRef(null);
  const previousFocus = useRef(null);
  const [confirmInput, setConfirmInput] = useState('');

  // 첫 렌더 — 이전 포커스 저장 + 진입 포커스 + body 스크롤락
  useEffect(() => {
    if (!open) return;
    previousFocus.current = document.activeElement;
    setConfirmInput('');
    const focusTarget = requireText ? inputRef.current : cancelRef.current;
    setTimeout(() => focusTarget?.focus(), 0);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prevOverflow;
      previousFocus.current?.focus?.();
    };
  }, [open, requireText]);

  const handleKey = useCallback((e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if (e.key !== 'Tab') return;
    const root = dialogRef.current;
    if (!root) return;
    const focusable = root.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, [onCancel]);

  if (!open) return null;

  const isDanger = tone === 'danger';
  const requireMatched = !requireText || confirmInput === requireText;

  return (
    <div
      className="fixed inset-0 z-[200] bg-black/55 backdrop-blur-[1px] flex items-center justify-center p-4"
      onClick={onCancel}
      onKeyDown={handleKey}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        aria-describedby="confirm-modal-desc"
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col fade-in"
      >
        <div className="flex items-start gap-3 px-5 pt-5">
          <div
            className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
              isDanger ? 'bg-red-100 text-red-600' : 'bg-blue-50 text-blue-600'
            }`}
            aria-hidden="true"
          >
            {isDanger ? <AlertTriangle size={18} /> : <Info size={18} />}
          </div>
          <div className="flex-1">
            <h3 id="confirm-modal-title" className="text-base font-bold text-gray-900 leading-snug">
              {title}
            </h3>
            <p id="confirm-modal-desc" className="text-xs text-gray-600 mt-1.5 leading-relaxed whitespace-pre-line">
              {message}
            </p>
          </div>
          <button
            onClick={onCancel}
            aria-label={'\uB2EB\uAE30'}
            className="p-1.5 -mt-1 -mr-1 rounded-lg text-gray-400 hover:bg-gray-100"
          >
            <X size={16} />
          </button>
        </div>

        {requireText && (
          <div className="px-5 pt-3">
            <label className="block text-[11px] font-medium text-gray-700 mb-1">
              {'\uD655\uC778\uC744 \uC704\uD574 '}
              <code className="px-1 py-0.5 bg-gray-100 text-red-600 rounded font-mono text-[10px]">{requireText}</code>
              {' \uB97C \uC785\uB825\uD558\uC138\uC694'}
            </label>
            <input
              ref={inputRef}
              type="text"
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value)}
              autoComplete="off"
              spellCheck="false"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
            />
          </div>
        )}

        <div className="flex items-center justify-end gap-2 px-5 py-4 mt-2">
          <button
            ref={cancelRef}
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            {cancelLabel}
          </button>
          <button
            onClick={() => requireMatched && onConfirm()}
            disabled={!requireMatched}
            className={`px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${
              isDanger ? 'bg-red-600 hover:bg-red-700' : 'bg-accent hover:bg-accent-dark'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default FocusTrapModal;
