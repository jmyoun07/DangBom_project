import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceArea, ReferenceLine, ResponsiveContainer } from 'recharts';

/**
 * 수치 추이 라인차트.
 *
 * Props:
 *   - data:      [{ month: '2025-09' | '9월' | Date, value: number }] (B3: 연도 표기 권장)
 *   - unit:      'mg/dL', '%', ...
 *   - color:     라인 색
 *   - title:     차트 제목
 *   - reference: { lo, hi }  ← 정상 범위. 회색 ReferenceArea 로 가시화 (B3)
 *   - critical:  number       ← cut-off 임계선. 빨간 점선 ReferenceLine 으로 표시
 *   - yPad:      number       ← Y 도메인 padding (기본 10%)
 */
export default function TrendChart({
  data = [],
  unit = '',
  color = 'var(--color-accent, #3b82f6)',
  title = '',
  reference = null,
  critical = null,
  yPad = 0.1,
}) {
  const currentValue = data.length > 0 ? data[data.length - 1].value : null;

  // Y 도메인 — 데이터 + 참조 범위 모두 포함하도록 자동 계산
  const yDomain = (() => {
    const vals = data.map((d) => d.value).filter((v) => Number.isFinite(v));
    if (!vals.length) return ['auto', 'auto'];
    let min = Math.min(...vals);
    let max = Math.max(...vals);
    if (reference) {
      if (Number.isFinite(reference.lo)) min = Math.min(min, reference.lo);
      if (Number.isFinite(reference.hi)) max = Math.max(max, reference.hi);
    }
    if (Number.isFinite(critical)) {
      min = Math.min(min, critical);
      max = Math.max(max, critical);
    }
    const span = Math.max(1, max - min);
    return [Math.max(0, min - span * yPad), max + span * yPad];
  })();

  // X축 라벨 포매터 — Date 객체 / ISO 문자열 / 그냥 라벨 모두 지원
  const formatX = (v) => {
    if (!v) return '';
    if (v instanceof Date) {
      const m = v.getMonth() + 1;
      const y = String(v.getFullYear()).slice(2);
      return `'${y}.${m}`;
    }
    // 'YYYY-MM' or 'YYYY-MM-DD' → 'YY.M'
    const iso = /^(\d{4})-(\d{1,2})/.exec(String(v));
    if (iso) return `'${iso[1].slice(2)}.${parseInt(iso[2], 10)}`;
    return v;
  };

  return (
    <div className="bg-white rounded-xl p-4 border border-gray-100">
      <div className="flex justify-between items-center mb-3">
        <h4 className="text-sm font-semibold text-gray-700">{title}</h4>
        {currentValue !== null && (
          <span className="text-lg font-bold tabular-nums" style={{ color }}>
            {currentValue}
            <span className="text-xs font-normal text-gray-400 ml-1">{unit}</span>
          </span>
        )}
      </div>
      <div role="img" aria-label={`${title} \uCD94\uC774 \uCC28\uD2B8`}>
        <ResponsiveContainer width="100%" height={120}>
          <LineChart data={data} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis
              dataKey="month"
              tickFormatter={formatX}
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
              width={36}
            />
            <Tooltip
              contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '12px' }}
              labelFormatter={formatX}
              formatter={(value) => [`${value} ${unit}`, title]}
            />
            {reference && Number.isFinite(reference.lo) && Number.isFinite(reference.hi) && (
              <ReferenceArea
                y1={reference.lo}
                y2={reference.hi}
                fill="#10b981"
                fillOpacity={0.06}
                stroke="#10b981"
                strokeOpacity={0.15}
                label={{ value: '\uC815\uC0C1 \uBC94\uC704', position: 'insideTopRight', fontSize: 9, fill: '#10b981' }}
              />
            )}
            {Number.isFinite(critical) && (
              <ReferenceLine
                y={critical}
                stroke="#ef4444"
                strokeDasharray="4 3"
                strokeWidth={1.2}
                label={{ value: `cut-off ${critical}`, position: 'right', fontSize: 9, fill: '#ef4444' }}
              />
            )}
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={{ r: 4, fill: color, strokeWidth: 2, stroke: '#fff' }}
              activeDot={{ r: 6 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
