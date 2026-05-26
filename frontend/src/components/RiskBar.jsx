import { scoreToLevel, riskColorFor, RISK_LEVELS } from '../theme';

/**
 * 가로 위험도 진행바.
 * - score 로 색 결정 (scoreToLevel 기반 — 백엔드 _level() 과 cut-off 동일 60/30).
 * - level prop 을 명시하면 그 색을 강제 사용.
 * - NOT_READY/PENDING 레벨은 회색 바 + 40% 투명도.
 */
export default function RiskBar({ score = 0, level, height = 'h-1.5', className = '' }) {
  const clamped = Math.max(0, Math.min(100, score));
  const effectiveLevel = level || scoreToLevel(clamped) || RISK_LEVELS.PENDING;
  const c = riskColorFor(effectiveLevel);

  const isPending = effectiveLevel === RISK_LEVELS.PENDING || effectiveLevel === RISK_LEVELS.NOT_READY;

  return (
    <div
      className={`w-full bg-gray-100 rounded-full ${height} ${className}`}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`\uC704\uD5D8\ub3c4 ${clamped}/100, ${c.ariaLabel}`}
    >
      <div
        className={`${height} rounded-full transition-all duration-500 ${c.bar} ${isPending ? 'opacity-40' : ''}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
