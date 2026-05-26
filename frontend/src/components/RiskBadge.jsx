import { RISK_LEVELS, RISK_COLORS, riskColorFor } from '../theme';

/**
 * 위험도 배지 — 색 + 아이콘 병기 (색각 이상 배려).
 * - 고위험: ▲ red (red-50 / red-700 = AA 7:1+)
 * - 중위험: ◆ amber (amber-50 / amber-700 = AA 4.5:1+) ※ yellow-100/600 대비 문제 해소
 * - 저위험: ● emerald
 * - 분석중(level=null) : 점 + 회색 펄스
 */
export default function RiskBadge({ level, showIcon = true, className = '' }) {
  if (!level) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500 border border-gray-200 ${className}`}
        role="status"
        aria-label={RISK_LEVELS.PENDING}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse" aria-hidden="true" />
        {RISK_LEVELS.PENDING}
      </span>
    );
  }

  const c = riskColorFor(level);
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${c.badge} ${className}`}
      aria-label={c.ariaLabel}
    >
      {showIcon && (
        <span aria-hidden="true" className="text-[10px] leading-none">
          {c.icon}
        </span>
      )}
      <span>{level}</span>
    </span>
  );
}
