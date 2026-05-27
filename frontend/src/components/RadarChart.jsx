import { Radar, RadarChart as RechartsRadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';
import { DISEASE_LABELS, PENDING_DISEASE_KEYS, RISK_COLORS, RISK_LEVELS, scoreToLevel } from '../theme';

/**
 * 6개 합병증 위험 레이더 차트.
 * - 고위험 꼭짓점: 빨간 코어 + 맥동 후광 (색각 대비 + 시각 강조).
 * - 중위험 / 저위험: amber / emerald.
 * - 준비 중 (ML 미구현): 회색 점 + 축 라벨 이탤릭 + '›' 접미.
 *
 * 주의: 현재 neuro/dementia/cerebro 는 ML 모델이 없어 0 값으로 그려짐 (추후 모델 배포 시 해소).
 */

const modelAliases = {
  kidney: 'kidney_disease',
  retina: 'retinopathy',
  cardio: 'cardiovascular',
  neuro: 'neuropathy',
  cerebro: 'cerebrovascular',
};

function readRadarDatum(data, key, pending) {
  const raw = data[key] ?? data[modelAliases[key]];
  if (raw && typeof raw === 'object') {
    const numericScore = Number(raw.score ?? raw.value ?? 0);
    const value = Number.isFinite(numericScore) ? numericScore : 0;
    return {
      value,
      level: pending ? null : (raw.level || scoreToLevel(value)),
    };
  }

  const numericScore = Number(raw ?? 0);
  const value = Number.isFinite(numericScore) ? numericScore : 0;
  return {
    value,
    level: pending ? null : scoreToLevel(value),
  };
}

// 꼭짓점 점 — level 에 따라 색·크기·애니메이션 분기
function CustomDot(props) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  const level = payload?.level;
  const pending = payload?.pending;

  if (pending) {
    // ML 미구현 — 축소된 회색 점
    return <circle cx={cx} cy={cy} r={2.5} fill="#d1d5db" stroke="#ffffff" strokeWidth={1} />;
  }

  if (level === RISK_LEVELS.HIGH) {
    const c = RISK_COLORS[RISK_LEVELS.HIGH];
    return (
      <g>
        <circle cx={cx} cy={cy} r={9} fill={c.fill} opacity={0.25}>
          <animate attributeName="r" values="8;14;8" dur="1.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.35;0.05;0.35" dur="1.4s" repeatCount="indefinite" />
        </circle>
        <circle cx={cx} cy={cy} r={5} fill={c.fill} stroke="#ffffff" strokeWidth={1.5} />
      </g>
    );
  }

  if (level === RISK_LEVELS.MID) {
    const c = RISK_COLORS[RISK_LEVELS.MID];
    return <circle cx={cx} cy={cy} r={3.5} fill={c.fill} stroke="#ffffff" strokeWidth={1} />;
  }

  const c = RISK_COLORS[RISK_LEVELS.LOW];
  return <circle cx={cx} cy={cy} r={3} fill={c.fill} stroke="#ffffff" strokeWidth={1} />;
}

export default function RadarChartComponent({ data = {} }) {
  const chartData = Object.entries(DISEASE_LABELS).map(([key, label]) => {
    const pending = PENDING_DISEASE_KEYS.has(key);
    const { value, level } = readRadarDatum(data, key, pending);
    return {
      key,
      subject: label,
      value,
      level,
      pending,
      fullMark: 100,
    };
  });

  // 축 라벨 — 고위험 강조, 준비 중 회색 이탤릭
  const CustomTick = ({ x, y, payload, textAnchor, index }) => {
    const item = chartData[index];
    const level = item?.level;
    const pending = item?.pending;
    const isHigh = level === RISK_LEVELS.HIGH;
    return (
      <text
        x={x}
        y={y}
        textAnchor={textAnchor}
        dominantBaseline="central"
        fill={pending ? '#9ca3af' : isHigh ? '#dc2626' : '#4b5563'}
        fontSize={12}
        fontWeight={pending ? 400 : isHigh ? 700 : 500}
        fontStyle={pending ? 'italic' : 'normal'}
      >
        {payload.value}{pending ? ' ›' : ''}
      </text>
    );
  };

  // 영역 색 — 고위험 1개 이상이면 빨강 톤, 아니면 accent indigo
  const highCount = chartData.filter((d) => d.level === RISK_LEVELS.HIGH).length;
  const midCount  = chartData.filter((d) => d.level === RISK_LEVELS.MID).length;
  const stroke = highCount > 0 ? RISK_COLORS[RISK_LEVELS.HIGH].stroke
                : midCount > 0  ? RISK_COLORS[RISK_LEVELS.MID].stroke
                : '#6366f1';
  const fill   = highCount > 0 ? RISK_COLORS[RISK_LEVELS.HIGH].rgba(0.22)
                : midCount > 0  ? RISK_COLORS[RISK_LEVELS.MID].rgba(0.22)
                : 'rgba(99, 102, 241, 0.3)';

  return (
    <div className="flex flex-col">
      <ResponsiveContainer width="100%" height={300}>
        <RechartsRadarChart data={chartData} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#e5e7eb" />
          <PolarAngleAxis dataKey="subject" tick={CustomTick} />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={{ fontSize: 9, fill: '#9ca3af' }}
            tickCount={5}
          />
          <Radar
            name="\uC704\ud5d8\uc810\uc218"
            dataKey="value"
            stroke={stroke}
            strokeWidth={2}
            fill={fill}
            fillOpacity={0.6}
            dot={CustomDot}
            isAnimationActive
          />
        </RechartsRadarChart>
      </ResponsiveContainer>
      {/* 범례 — 색각 대비 포함. v2.1.7: 준비 중 범례는 PENDING 있을 때만 노출 */}
      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-gray-600 px-2 pt-1">
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="text-red-500 leading-none">▲</span>
          <span>{RISK_LEVELS.HIGH} (≥ 60)</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="text-amber-500 leading-none">◆</span>
          <span>{RISK_LEVELS.MID} (모델 기준)</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="text-emerald-500 leading-none">●</span>
          <span>{RISK_LEVELS.LOW} (모델 기준 미만)</span>
        </span>
        {PENDING_DISEASE_KEYS.size > 0 && (
          <span className="inline-flex items-center gap-1 italic text-gray-400">
            <span aria-hidden="true">›</span>
            <span>분석 진행 중</span>
          </span>
        )}
      </div>
      <p className="text-[10px] text-gray-400 text-center mt-1">
        축 길이 = 0–100 위험점수, 점 색 = backend level 우선
      </p>
    </div>
  );
}
