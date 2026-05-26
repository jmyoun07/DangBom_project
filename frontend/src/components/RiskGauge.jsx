import { RISK_LEVELS, riskColorFor } from '../theme';

/**
 * 반원형 게이지 — 환자 보여주기용 (점수 숫자 대신 레벨 텍스트만).
 * - 반원 arc 길이에 맞춘 dasharray (π·r) 로 fill 비율을 정확히 계산.
 * - 색상은 theme.js RISK_COLORS 기준 (mid = amber 통일).
 */
export default function RiskGauge({ score = 0, level = RISK_LEVELS.MID }) {
  const clamped = Math.max(0, Math.min(100, score));
  const { stroke, ariaLabel, icon } = riskColorFor(level);

  // 반원 둘레 = π · r
  const radius = 70;
  const arcLen = Math.PI * radius;
  const offset = arcLen - (clamped / 100) * arcLen;

  return (
    <div
      className="flex flex-col items-center"
      role="img"
      aria-label={`\uc704\ud5d8\ub3c4 \uac8c\uc774\uc9c0: ${ariaLabel}`}
    >
      <svg viewBox="0 0 160 100" className="w-full max-w-[220px]" aria-hidden="true">
        {/* Background arc */}
        <path
          d="M 10 80 A 70 70 0 0 1 150 80"
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Value arc */}
        <path
          d="M 10 80 A 70 70 0 0 1 150 80"
          fill="none"
          stroke={stroke}
          strokeWidth="12"
          strokeLinecap="round"
          pathLength={arcLen}
          strokeDasharray={arcLen}
          strokeDashoffset={offset}
          className="transition-all duration-700"
        />
        {/* Center text — 레벨만, 색각 아이콘 병기 */}
        <text x="80" y="66" textAnchor="middle" fill={stroke} fontSize="18" fontWeight="700">
          <tspan>{icon}</tspan>
          <tspan dx="4">{level}</tspan>
        </text>
        <text x="80" y="90" textAnchor="middle" fill="#9ca3af" fontSize="9" letterSpacing="1.5">
          RISK GAUGE
        </text>
      </svg>
    </div>
  );
}
