import { useState } from 'react';
import { AlertTriangle, Info, ShieldAlert } from 'lucide-react';
import RiskBadge from './RiskBadge';
import RiskBar from './RiskBar';
import { useTheme } from '../contexts/ThemeContext';

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

// 나이 → KNHANES 10세 단위 연령대 버킷 (질환 무관 — 나이만으로 결정).
//   percentile 코호트 데이터가 없는 모델(선별 3종)도 '동일 연령대 (n~n+9)' 표시에 사용.
function ageBucket(age) {
  const a = Number(age);
  if (!Number.isFinite(a) || a < 19) return null;
  if (a < 30) return '19-29';
  if (a < 40) return '30-39';
  if (a < 50) return '40-49';
  if (a < 60) return '50-59';
  if (a < 70) return '60-69';
  if (a < 80) return '70-79';
  return '80+';
}

export default function RiskCard({
  name,
  englishName,
  type,
  level,
  metricLabel,
  metricValue,
  contributions = null,   // v2.4.0: 이 환자 예측에 기여한 변수(SHAP) 상위 N — 있으면 환자별 근거 표시
  score,
  available = true,
  percentile = null,
  fold = null,
  age = null,
  clinicalFlags = [],
  showScore = false,        // true: 메트릭 자리에 '위험지수 N/100' (대시보드)
  showPercentile = true,    // 백분위('100명 중 N번째') 표시 여부
  insufficient = false,     // v2.2.8: 필수 검사 누락(추정 안 함) → '데이터 부족' 표시
  missingRequired = null,   // 누락된 필수 검사 라벨 배열
}) {
  // 설정 '영문 합병증명 함께 표시' 를 실제 영문명 표시에 연결
  const { settings } = useTheme();
  const showEnglish = settings?.showEnglishLabels !== false;
  const displayMetricLabel = showScore ? '위험지수' : metricLabel;
  const displayMetricValue = showScore ? (score == null ? '--' : `${Math.round(score)}/100`) : metricValue;
  const hasContrib = Array.isArray(contributions) && contributions.length > 0;
  // v2.1.2 \u2014 KNHANES \uB3D9\uC77C \uC5F0\uB839\uB300 \uBC31\uBD84\uC704 \uD45C\uC2DC.
  // percentile = { percentile: 73, top_percent: 27, bucket: "60-69", n: 1299 }
  //   \u2193 "\uC0C1\uC704 X%" \uB85C \uD45C\uC2DC (X = 100 - percentile)
  // v2.2.7: 환자도 보는 화면이라 임상 사유/안전망 경고 텍스트(예: "최소 중위험 안전망",
  //   "HbA1c≥11 → 고위험")를 노출하지 않는다 — "수치 높으면 무조건 위험"이라는 오해 방지.
  //   원복: 아래 [] 를 clinicalFlags 필터로 되돌리면 경고 버튼/사유텍스트/패널이 다시 표시됨.
  const flags = [];
  void clinicalFlags;
  // v2.2.2 (F5): 등급을 끌어올린 임상 사유(affects_level/danger)는 항상 노출 →
  //   "정상 수치인데 왜 위험?" 의 답을 클릭 없이 바로 보여준다. (예측 로딩 타이밍과 무관)
  const primaryReason = flags.find((f) => f?.affects_level || f?.severity === 'danger');
  const [flagsOpen, setFlagsOpen] = useState(false);
  // v2.2.7: 평가 단계라 '선별용 모델(정확도 제한적)' 배지/코멘트를 표시하지 않는다.
  //   (개발자가 인지 중, 출시 전 병원데이터로 세부조정 시 재검토) — 원복: 앞의 false 제거.
  const isScreening = false;  // v2.2.7: 선별 라벨 비표시(사용자 요청). 원복 시 modelRole==='screening'
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
            {showEnglish && englishName && (
              <p className="text-[10px] text-gray-400 uppercase tracking-wider truncate">{englishName}</p>
            )}
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
            <div className="flex items-center gap-1">
              {isScreening && (
                <span
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-slate-100 text-slate-500 border border-slate-200 whitespace-nowrap"
                  title="\uC800\uC815\uD655\uB3C4 \uC120\uBCC4 \uBAA8\uB378 \u2014 \uCC38\uACE0\uC6A9, \uC784\uC0C1 \uD655\uC778 \uD544\uC694"
                >
                  {'\uC120\uBCC4'}
                </span>
              )}
              <RiskBadge level={level} />
            </div>
          ) : insufficient ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600 border border-gray-300 whitespace-nowrap">
              <span aria-hidden="true">{'\u26A0'}</span>{'\uB370\uC774\uD130 \uBD80\uC871'}
            </span>
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
            <span className="text-xs text-gray-500 inline-flex items-center gap-1">
              {displayMetricLabel}
              {/* v2.4.0: 이 환자 예측에 실제로 기여한 변수임을 표시 (고정 지표와 구분) */}
              {!showScore && hasContrib && (
                <span
                  className="text-[9px] px-1 py-px rounded bg-accent-soft text-accent font-medium"
                  title="이 환자의 예측에 가장 크게 기여한 변수입니다 (환자마다 다름)"
                >
                  {'환자별'}
                </span>
              )}
            </span>
            <span className="text-sm font-bold text-gray-800">{displayMetricValue}</span>
          </div>
          <RiskBar score={score || 0} level={level} />
          {/* 2·3순위 기여 변수 — 1순위만으로는 근거가 얇아 함께 보여준다 */}
          {!showScore && hasContrib && contributions.length > 1 && (
            <p className="mt-1.5 text-[10px] text-gray-400 leading-tight">
              {'다음 요인: '}
              {contributions.slice(1, 3).map((c) => `${c.label} ${c.value}${c.unit}`).join(' · ')}
            </p>
          )}
          {primaryReason && (
            <p className="mt-1.5 text-[10px] text-amber-700 leading-tight">
              {primaryReason.message}
            </p>
          )}
          {isScreening && (
            <p className="mt-1 text-[10px] text-slate-400 leading-tight">
              {'선별용 모델(정확도 제한적) — 임상 확인 필요'}
            </p>
          )}
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
          {showPercentile && available && (fold?.bucket || percentile?.bucket || ageBucket(age)) && (() => {
            // \uB3D9\uC77C \uC5F0\uB839\uB300(n~n+9)\uB294 \uB098\uC774\uB9CC\uC73C\uB85C \uACB0\uC815 \u2192 \uBAA8\uB4E0 \uBAA8\uB378(\uC120\uBCC4 \uD3EC\uD568)\uC5D0 \uD45C\uC2DC.
            //   \uCF54\uD638\uD2B8 \uB370\uC774\uD130\uAC00 \uC788\uC73C\uBA74(\uC784\uC0C1 \uBAA8\uB378) '\uB610\uB798 \uD3C9\uADE0 \uB300\uBE44 N\uBC30'(fold)\uB3C4 \uD568\uAED8 \uD45C\uC2DC.
            //   v2.2.7: \uC808\uB300 \uC704\uD5D8\uC774 \uB0AE\uC544\uB3C4 \uB610\uB798 \uB300\uBE44 \uB192\uC744 \uC218 \uC788\uC5B4, \uC624\uD574\uB97C \uC8FC\uB358 '\uC0C1\uC704 X%' \uB300\uC2E0
            //   \uBC30\uC218(fold)\uB85C \uC9C1\uAD00\uD654\uD558\uACE0 \uC0C9\uC740 \uC911\uB9BD(\uD68C\uC0C9)\uC73C\uB85C \u2014 \uB4F1\uAE09 \uBC30\uC9C0\uC640 \uC2DC\uAC01 \uCDA9\uB3CC \uC81C\uAC70.
            const bucket = fold?.bucket ?? percentile?.bucket ?? ageBucket(age);
            const topN = (percentile && typeof percentile.top_percent === 'number')
              ? Math.max(1, Math.min(99, Math.round(percentile.top_percent))) : null;
            const label = topN != null ? `100\uBA85 \uC911 ${topN}\uBC88\uC9F8\uB85C \uC704\uD5D8\uD55C \uD3B8` : null;
            return (
              <div
                className="mt-2 flex items-center justify-between"
                title={topN != null ? `\uB3D9\uC77C \uC5F0\uB839\uB300 ${bucket} \u00B7 \uC0C1\uC704 ${topN}% (KNHANES ${percentile.n}\uBA85)` : `\uB3D9\uC77C \uC5F0\uB839\uB300 ${bucket}`}
              >
                <span className="text-[10px] text-gray-400">{`\uB3D9\uC77C \uC5F0\uB839\uB300 (${bucket})`}</span>
                {label && <span className="text-[10px] font-medium tabular-nums text-gray-500">{label}</span>}
              </div>
            );
          })()}
        </>
      )}

      {!available && insufficient && (
        <div className="py-2">
          <p className="text-xs text-gray-500 text-center">{'\uD544\uC218 \uAC80\uC0AC \uC218\uCE58\uAC00 \uC5C6\uC5B4 \uC608\uCE21\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.'}</p>
          {Array.isArray(missingRequired) && missingRequired.length > 0 && (
            <p className="mt-1 text-[10px] text-gray-400 text-center leading-tight">
              {'\uB204\uB77D: '}{missingRequired.slice(0, 4).join(', ')}{missingRequired.length > 4 ? ` \uC678 ${missingRequired.length - 4}\uAC1C` : ''}
            </p>
          )}
        </div>
      )}
      {!available && !insufficient && (
        <div className="text-center py-3">
          <p className="text-xs text-gray-400">{'\uC54C\uACE0\uB9AC\uC998 \uC5F0\uB3D9 \uC608\uC815'}</p>
        </div>
      )}
    </div>
  );
}
