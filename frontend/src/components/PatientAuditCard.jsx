import { useEffect, useState } from 'react';
import { History, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import api from '../api/client';
import { prodSafeError } from '../theme';

// 필드명 → 한글 라벨 (검사·생활습관·기본 정보)
const FIELD_LABELS = {
  // 메타
  name: '이름',
  chart_no: '차트번호',
  dob: '생년월일',
  sex: '성별',
  phone: '연락처',
  exam_date: '검사일',
  // 혈당
  hba1c: 'HbA1c',
  c_peptide: 'C-peptide',
  fbg: '공복혈당',
  he_insulin: '인슐린',
  // 간 / 신장
  ggt: 'GGT',
  alt: 'ALT',
  ast: 'AST',
  cr: 'Cr',
  // 지질
  total_cholesterol: '총콜레스테롤',
  triglycerides: '중성지방',
  hdl: 'HDL',
  ldl: 'LDL',
  // 혈압 / 신체
  sbp: '수축기혈압',
  dbp: '이완기혈압',
  bmi: 'BMI',
  height: '키',
  weight: '몸무게',
  // 소변
  he_upro: '단백뇨',
  he_uglu: '요당',
  he_ubld: '요잠혈',
  urine_bil: '요빌리루빈',
  urine_uro: '요유로빌리노겐',
  urine_ket: '요케톤',
  urine_nit: '요아질산염',
  urine_ph: '요pH',
  urine_sg: '요비중',
  // 과거력 / 당뇨
  hypertension: '고혈압',
  dm_diagnosis_age: '당뇨 진단 나이',
  dm_medication: '당뇨약 복용',
  insulin_medication: '인슐린 투약',
  // 생활습관
  smoking: '흡연',
  drinking: '음주',
  exercise: '운동',
  sleep_hours: '수면시간',
  visceral_fat: '내장지방',
  // 시스템
  risk_level: '위험도',
};

function fmt(v) {
  if (v === null || v === undefined || v === '') return '\u2014';  // — em-dash
  return String(v);
}

function timeAgo(iso) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return '\uBC29\uAE08';     // 방금
  if (m < 60) return `${m}\uBD84 \uC804`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}\uC2DC\uAC04 \uC804`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}\uC77C \uC804`;
  return new Date(iso).toLocaleDateString('ko-KR');
}

export default function PatientAuditCard({ patientId, refreshKey = 0 }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!patientId) return;
    try {
      setLoading(true);
      setError(null);
      const res = await api.get(`/patients/${patientId}/audit`, { params: { limit: 50 } });
      setRows(res.data?.data || []);
    } catch (e) {
      prodSafeError('PatientAuditCard.load')(e);
      setError('\uC774\uB825\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, refreshKey]);

  const visible = expanded ? rows : rows.slice(0, 3);

  return (
    <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-800 inline-flex items-center gap-1.5">
          <History size={14} className="text-gray-500" aria-hidden="true" />
          {'\uC218\uC815 \uC774\uB825'}
        </h3>
        <button
          onClick={load}
          aria-label="\uC218\uC815 \uC774\uB825 \uC0C8\uB85C\uACE0\uCE68"
          className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
          disabled={loading}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} aria-hidden="true" />
        </button>
      </div>

      {error && (
        <p className="text-[11px] text-red-500" role="alert">{error}</p>
      )}

      {!error && !loading && rows.length === 0 && (
        <p className="text-[11px] text-gray-400">{'\uC218\uC815 \uC774\uB825\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.'}</p>
      )}

      {!error && rows.length > 0 && (
        <ul className="space-y-2" aria-label="\uC218\uC815 \uC774\uB825 \uBAA9\uB85D">
          {visible.map((r) => {
            const label = FIELD_LABELS[r.field_name] || r.field_name;
            const isSystem = r.actor && r.actor.startsWith('system');
            return (
              <li key={r.id} className="text-[11px] leading-relaxed">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-gray-700 truncate" title={r.field_name}>{label}</span>
                  <span className="text-gray-400 shrink-0 tabular-nums" title={r.changed_at}>
                    {timeAgo(r.changed_at)}
                  </span>
                </div>
                <div className="text-gray-500 mt-0.5">
                  <span className="line-through text-gray-400" title={`\uC774\uC804: ${fmt(r.old_value)}`}>{fmt(r.old_value)}</span>
                  <span className="mx-1 text-gray-300" aria-hidden="true">{'\u2192'}</span>
                  <span className="font-semibold text-gray-700" title={`\uBCC0\uACBD\uD6C4: ${fmt(r.new_value)}`}>{fmt(r.new_value)}</span>
                  {isSystem && (
                    <span className="ml-2 inline-block text-[9px] text-gray-400 border border-gray-200 rounded px-1 py-0">
                      {r.actor.includes('ml') ? 'ML' : 'system'}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {rows.length > 3 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 inline-flex items-center gap-1 text-[11px] text-accent font-medium hover:underline"
          aria-expanded={expanded}
        >
          {expanded ? (
            <>{'\uC811\uAE30'} <ChevronUp size={11} aria-hidden="true" /></>
          ) : (
            <>{'\uC804\uCCB4 \uBCF4\uAE30'} ({rows.length}) <ChevronDown size={11} aria-hidden="true" /></>
          )}
        </button>
      )}
    </div>
  );
}
