import { useState } from 'react';
import { AlertTriangle, Info, ShieldAlert } from 'lucide-react';
import RiskBadge from './RiskBadge';
import RiskBar from './RiskBar';

const iconMap = {
  'kidney': '\uD83E\uDEC0',
  'dementia': '\uD83E\uDDE0',
  'cardiovascular': '\u2764\uFE0F',
  'neuropathy': '\uD83E\uDDB6',
  'cerebrovascular': '\uD83C\uDF0A',
  'retinopathy': '\uD83D\uDC41\uFE0F',
};

const flagStyles = {
  danger: {
    button: 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100',
    panel: 'bg-red-50 border-red-200 text-red-800',
    source: 'text-red-500',
    Icon: ShieldAlert,
  },
  warning: {
    button: 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100',
    panel: 'bg-amber-50 border-amber-200 text-amber-800',
    source: 'text-amber-600',
    Icon: AlertTriangle,
  },
  info: {
    button: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100',
    panel: 'bg-blue-50 border-blue-200 text-blue-800',
    source: 'text-blue-500',
    Icon: Info,
  },
};

function flagSeverity(flags) {
  if (flags.some((f) => f?.severity === 'danger')) return 'danger';
  if (flags.some((f) => f?.severity === 'warning')) return 'warning';
  return 'info';
}

export default function RiskCard({
  name,
  englishName,
  type,
  level,
  metricLabel,
  metricValue,
  score,
  available = true,
  percentile = null,
  clinicalFlags = [],
}) {
  // v2.1.2 \u2014 KNHANES \uB3D9\uC77C \uC5F0\uB839\uB300 \uBC31\uBD84\uC704 \uD45C\uC2DC.
  // percentile = { percentile: 73, top_percent: 27, bucket: "60-69", n: 1299 }
  //   \u2193 "\uC0C1\uC704 X%" \uB85C \uD45C\uC2DC (X = 100 - percentile)
  const flags = Array.isArray(clinicalFlags)
    ? clinicalFlags.filter((f) => f && typeof f === 'object' && f.message)
    : [];
  const [flagsOpen, setFlagsOpen] = useState(false);
  const severity = flagSeverity(flags);
  const flagStyle = flagStyles[severity];
  const FlagIcon = flagStyle.Icon;

  return (
    <div className="bg-white rounded-xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow min-w-0 break-keep">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="text-xl shrink-0" aria-hidden="true">{iconMap[type] || '\u2B50'}</span>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-gray-800 leading-tight">{name}</h3>
            <p className="text-[10px] text-gray-400 uppercase tracking-wider truncate">{englishName}</p>
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-1.5">
          {available && flags.length > 0 && (
            <button
              type="button"
              onClick={() => setFlagsOpen((open) => !open)}
              className={`inline-flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${flagStyle.button}`}
              title={flags.map((f) => f.message).join('\n')}
              aria-label="임상 주의 신호"
              aria-expanded={flagsOpen}
            >
              <FlagIcon size={14} aria-hidden="true" />
            </button>
          )}
          {available ? (
            <RiskBadge level={level} />
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-400 border border-gray-200 whitespace-nowrap">
              {'\uBD84\uC11D \uC900\uBE44\uC911'}
            </span>
          )}
        </div>
      </div>

      {available && (
        <>
          <div className="flex justify-between items-baseline mb-2">
            <span className="text-xs text-gray-500">{metricLabel}</span>
            <span className="text-sm font-bold text-gray-800">{metricValue}</span>
          </div>
          <RiskBar score={score || 0} />
          {flagsOpen && flags.length > 0 && (
            <div className={`mt-3 rounded-lg border px-3 py-2 ${flagStyle.panel}`}>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold mb-1">
                <FlagIcon size={12} aria-hidden="true" />
                <span>임상 주의 신호</span>
              </div>
              <ul className="space-y-1.5">
                {flags.map((flag, idx) => (
                  <li key={`${flag.type || 'flag'}-${idx}`} className="text-[11px] leading-relaxed">
                    <span>{flag.message}</span>
                    {flag.source && (
                      <span className={`ml-1 ${flagStyle.source}`}>({flag.source})</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {percentile != null && percentile.percentile != null && (() => {
            // \uC704\uD5D8\uB3C4 \uBC31\uBD84\uC704 (KNHANES \uCF54\uD638\uD2B8 \uB300\uBE44). \uD074\uC218\uB85D \uC704\uD5D8 \uB192\uC74C.
            const p = percentile.percentile;
            let label, colorCls;
            if (p >= 90) {
              label = `\uC704\uD5D8\uB3C4 \uC0C1\uC704 ${100 - p}% (\uACE0\uC704\uD5D8\uAD70)`;
              colorCls = 'text-red-600';
            } else if (p >= 70) {
              label = `\uC704\uD5D8\uB3C4 \uC0C1\uC704 ${100 - p}%`;
              colorCls = 'text-amber-600';
            } else if (p >= 30) {
              label = `\uD3C9\uADE0 \uC218\uC900 (\uBC31\uBD84\uC704 ${p})`;
              colorCls = 'text-gray-600';
            } else {
              label = `\uC548\uC804\uAD8C (\uBC31\uBD84\uC704 ${p})`;
              colorCls = 'text-emerald-600';
            }
            return (
              <div
                className="mt-2 flex items-center justify-between"
                title={`\uB3D9\uC77C \uC5F0\uB839\uB300 ${percentile.bucket} KNHANES \uCF54\uD638\uD2B8 ${percentile.n}\uBA85 \uC911 \uC704\uD5D8\uB3C4 \uBC31\uBD84\uC704 ${p}`}
              >
                <span className="text-[10px] text-gray-400">{`\uB3D9\uC77C \uC5F0\uB839\uB300 (${percentile.bucket})`}</span>
                <span className={`text-[10px] font-semibold tabular-nums ${colorCls}`}>{label}</span>
              </div>
            );
          })()}
        </>
      )}

      {!available && (
        <div className="text-center py-3">
          <p className="text-xs text-gray-400">{'\uC54C\uACE0\uB9AC\uC998 \uC5F0\uB3D9 \uC608\uC815'}</p>
        </div>
      )}
    </div>
  );
}
