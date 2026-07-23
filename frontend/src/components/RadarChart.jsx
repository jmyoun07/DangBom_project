import { Radar, RadarChart as RechartsRadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';
import { DISEASE_LABELS, PENDING_DISEASE_KEYS, RISK_COLORS, RISK_LEVELS, scoreToLevel } from '../theme';

/**
 * 6개 합병증 위험 레이더 차트.
 * - 고위험 꼭짓점: 빨간 코어 + 맥동 후광 (색각 대비 + 시각 강조).
 * - 중위험 / 저위험: amber / emerald.
 * - 준비 중 (ML 미구현): 회색 점 + 축 라벨 이탤릭 + '›' 접미.
 *
 * v2.1.7 이후 6개 모델 모두 연동됨 (PENDING_DISEASE_KEYS 는 비어 있음).
 * 준비 중 처리는 향후 모델 제외 시를 대비해 유지.
 */

const modelAliases = {
  kidney: 'kidney_disease',
  retina: 'retinopathy',
  cardio: 'cardiovascular',
  neuro: 'neuropathy',
  cerebro: 'cerebrovascular',
  dementia: 'dementia',
};

function readRadarDatum(data, key, pendingByConfig) {
  const raw = data[key] ?? data[modelAliases[key]];
  if (raw && typeof raw === 'object') {
    // v2.2.2 (H1): 임상 안전망 반영된 display_score 우선 — 배지(level)와 축 길이 정합.
    const numericScore = Number(raw.display_score ?? raw.score ?? raw.value ?? 0);
    const value = Number.isFinite(numericScore) ? numericScore : 0;
    // v2.2.10: 백엔드가 추가한 available / source 반영.
    //   source === 'heuristic' → ML 예측 실패로 대체된 참고값 (정상 예측이 아님).
    //   필드가 없는 옛 응답(undefined)은 기존과 동일하게 정상 표시 (하위호환).
    const unavailable = raw.available === false;
    const heuristic = raw.source === 'heuristic';
    const pending = pendingByConfig || unavailable;
    return {
      value,
      level: pending ? null : (raw.level || scoreToLevel(value)),
      pending,
      heuristic: heuristic && !pending,
    };
  }

  const numericScore = Number(raw ?? 0);
  const value = Number.isFinite(numericScore) ? numericScore : 0;
  return {
    value,
    level: pendingByConfig ? null : scoreToLevel(value),
    pending: pendingByConfig,
    heuristic: false,
  };
}

// 꼭짓점 점 — level 에 따라 색·크기·애니메이션 분기
function CustomDot(props) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  const level = payload?.level;
  const pending = payload?.pending;

  if (pending) {
    // ML 미구현 / available:false — 축소된 회색 점
    return <circle cx={cx} cy={cy} r={2.5} fill="#d1d5db" stroke="#ffffff" strokeWidth={1} />;
  }

  if (payload?.heuristic) {
    // v2.2.10: ML 예측 실패 → 휴리스틱 참고값. 등급색 대신 회색 속빈 점으로 명확히 구분.
    return <circle cx={cx} cy={cy} r={4} fill="#ffffff" stroke="#9ca3af" strokeWidth={1.8} strokeDasharray="2 1.5" />;
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
    const { value, level, pending, heuristic } = readRadarDatum(data, key, PENDING_DISEASE_KEYS.has(key));
    return {
      key,
      subject: label,
      value,
      level,
      pending,
      heuristic,
      fullMark: 100,
    };
  });

  // v2.2.10: 휴리스틱 대체(ML 예측 실패) 축 집계 — 범례/배너 표기용
  const heuristicItems = chartData.filter((d) => d.heuristic);
  const hasHeuristic = heuristicItems.length > 0;
  const scored = chartData.filter((d) => !d.pending);
  const allHeuristic = scored.length > 0 && heuristicItems.length === scored.length;

  // 축 라벨 — 고위험 강조, 준비 중 회색 이탤릭
  const CustomTick = ({ x, y, payload, textAnchor, index }) => {
    const item = chartData[index];
    const level = item?.level;
    const pending = item?.pending;
    const heuristic = item?.heuristic;
    const isHigh = level === RISK_LEVELS.HIGH;
    // 휴리스틱 대체값은 등급 강조 없이 회색 처리 + '*' 접미 (범례에서 의미 설명)
    const muted = pending || heuristic;
    return (
      <text
        x={x}
        y={y}
        textAnchor={textAnchor}
        dominantBaseline="central"
        fill={muted ? '#9ca3af' : isHigh ? '#dc2626' : '#4b5563'}
        fontSize={12}
        fontWeight={muted ? 400 : isHigh ? 700 : 500}
        fontStyle={muted ? 'italic' : 'normal'}
      >
        <title>{heuristic ? `${payload.value} — 모델 예측 불가, 참고값` : payload.value}</title>
        {payload.value}{pending ? ' ›' : heuristic ? ' *' : ''}
      </text>
    );
  };

  // 영역 색 — 고위험 1개 이상이면 빨강 톤, 아니면 accent indigo.
  //   전부 휴리스틱 대체면 등급색을 쓰지 않고 회색 (정상 예측으로 오인 방지).
  const highCount = chartData.filter((d) => d.level === RISK_LEVELS.HIGH).length;
  const midCount  = chartData.filter((d) => d.level === RISK_LEVELS.MID).length;
  const stroke = allHeuristic ? '#9ca3af'
                : highCount > 0 ? RISK_COLORS[RISK_LEVELS.HIGH].stroke
                : midCount > 0  ? RISK_COLORS[RISK_LEVELS.MID].stroke
                : '#6366f1';
  const fill   = allHeuristic ? 'rgba(156, 163, 175, 0.22)'
                : highCount > 0 ? RISK_COLORS[RISK_LEVELS.HIGH].rgba(0.22)
                : midCount > 0  ? RISK_COLORS[RISK_LEVELS.MID].rgba(0.22)
                : 'rgba(99, 102, 241, 0.3)';

  return (
    <div className="flex flex-col">
      {/* v2.2.10: 6개 축 전부 ML 예측 실패 → 참고값 대체임을 상단에 명시 */}
      {allHeuristic && (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2" role="status">
          <span aria-hidden="true" className="text-amber-500 text-[11px] leading-4">⚠</span>
          <p className="text-[11px] text-amber-800 leading-4">
            {'현재 예측 모델을 사용할 수 없어 모든 항목이 참고값(휴리스틱)으로 표시됩니다. 임상 판단에 사용하지 마세요.'}
          </p>
        </div>
      )}
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
        {/* 등급은 backend 모델 threshold(level) 기준 — 고정 컷(≥60 등) 표기는 혼동을 줘 제거 */}
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="text-red-500 leading-none">▲</span>
          <span>{RISK_LEVELS.HIGH}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="text-amber-500 leading-none">◆</span>
          <span>{RISK_LEVELS.MID}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="text-emerald-500 leading-none">●</span>
          <span>{RISK_LEVELS.LOW}</span>
        </span>
        {PENDING_DISEASE_KEYS.size > 0 && (
          <span className="inline-flex items-center gap-1 italic text-gray-400">
            <span aria-hidden="true">›</span>
            <span>분석 진행 중</span>
          </span>
        )}
        {hasHeuristic && (
          <span
            className="inline-flex items-center gap-1 italic text-gray-500"
            title={`모델 예측 불가 — 참고값: ${heuristicItems.map((d) => d.subject).join(', ')}`}
          >
            <span aria-hidden="true">*</span>
            <span>{'모델 예측 불가 — 참고값'}</span>
          </span>
        )}
      </div>
      <p className="text-[10px] text-gray-400 text-center mt-1">
        축 길이 = 0–100 위험점수 · 등급(점 색) = 모델별 기준(backend level) 우선
      </p>
    </div>
  );
}
