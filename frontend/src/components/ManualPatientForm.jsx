import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Save, AlertCircle, User, Calculator, Activity, FlaskConical, Beaker, Heart, Pill, Cigarette, Search, UserCheck } from 'lucide-react';
import api from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { prodSafeError } from '../theme';

// 불러오기 시 자동 채워지는 필드 (메타데이터 + 변하지 않는 환자 특성)
// 검사 수치(HbA1c, FBG, C-peptide, 혈압, 지질, 신체 계측, BMI, 소변)는 새로 입력해야 하므로 제외.
const PRELOAD_FIELDS = [
  'name', 'chart_no', 'dob', 'sex', 'phone',
  'dm_diagnosis_age',
  'dm_medication', 'insulin_medication', 'hypertension',
  'smoking', 'drinking', 'exercise', 'sleep_hours',
];

// 한 환자의 모든 변수를 수기로 입력. POST /patients 가 derived (BMI, eGFR, HOMA, age 등)
// 자동 계산 후 저장하므로, 폼은 원본값만 받는다.
//
// priority 분류:
//   required    — ML 모델 정확도에 핵심. 미입력 시 합병증 예측 신뢰도 크게 낮아짐.
//   recommended — 있으면 정확도 향상 / 합병증별 특정 모델 입력
//   optional    — 보조 지표. 없어도 모델 동작 (기본값으로 대체).
//
// 빈 값(""): 백엔드로 null 로 전송 → derived 가 안전한 기본값으로 보정.

const SECTIONS = [
  {
    title: '기본 정보',
    icon: User,
    fields: [
      { key: 'name',       label: '이름',          type: 'text',   priority: 'required',    placeholder: '홍길동' },
      { key: 'chart_no',   label: '차트번호',      type: 'text',   priority: 'required',    placeholder: 'CN-2026-0001' },
      { key: 'dob',        label: '생년월일',      type: 'date',   priority: 'required',    hint: '나이는 자동 계산' },
      { key: 'sex',        label: '성별',          type: 'select', priority: 'required',    options: [['M','남'], ['F','여']] },
      { key: 'phone',      label: '연락처',        type: 'tel',    priority: 'optional',    placeholder: '010-0000-0000' },
      { key: 'exam_date',  label: '검사일',        type: 'date',   priority: 'optional',    hint: '미입력시 오늘 (ML 예측에는 미사용)' },
    ],
  },
  {
    title: '신체 계측',
    icon: Calculator,
    fields: [
      { key: 'height',  label: '키',     unit: 'cm',     type: 'number', step: '0.1', priority: 'required' },
      { key: 'weight',  label: '몸무게', unit: 'kg',     type: 'number', step: '0.1', priority: 'required' },
      { key: 'bmi',     label: 'BMI',    unit: 'kg/m²', type: 'number', step: '0.1', priority: 'optional',    hint: '키·몸무게로 자동' },
      { key: 'sbp',     label: '수축기 혈압',  unit: 'mmHg', type: 'number', priority: 'required' },
      { key: 'dbp',     label: '이완기 혈압',  unit: 'mmHg', type: 'number', priority: 'required' },
    ],
  },
  {
    title: '혈당 · 인슐린',
    icon: Activity,
    fields: [
      { key: 'hba1c',     label: '당화혈색소 (HbA1c)', unit: '%',     type: 'number', step: '0.1',  priority: 'required' },
      { key: 'fbg',       label: '공복혈당',           unit: 'mg/dL', type: 'number', step: '0.1',  priority: 'required' },
      { key: 'c_peptide', label: 'C-peptide',          unit: 'ng/mL', type: 'number', step: '0.01', priority: 'required' },
    ],
  },
  {
    title: '지질 검사',
    icon: FlaskConical,
    fields: [
      { key: 'total_cholesterol', label: '총콜레스테롤', unit: 'mg/dL', type: 'number', priority: 'required' },
      { key: 'triglycerides',     label: '중성지방',     unit: 'mg/dL', type: 'number', priority: 'required' },
      { key: 'hdl',               label: 'HDL',          unit: 'mg/dL', type: 'number', priority: 'required' },
      { key: 'ldl',               label: 'LDL',          unit: 'mg/dL', type: 'number', priority: 'recommended', hint: '미입력시 Friedewald 계산' },
    ],
  },
  {
    title: '간 · 신장',
    icon: Beaker,
    fields: [
      { key: 'cr',  label: '크레아티닌 (Cr)', unit: 'mg/dL', type: 'number', step: '0.01', priority: 'required',    hint: 'eGFR 자동 계산' },
      { key: 'ast', label: 'AST',    unit: 'U/L',   type: 'number', step: '0.1', priority: 'recommended' },
      { key: 'alt', label: 'ALT',    unit: 'U/L',   type: 'number', step: '0.1', priority: 'recommended' },
      { key: 'ggt', label: 'GGT',    unit: 'U/L',   type: 'number', step: '0.1', priority: 'optional' },
    ],
  },
  {
    title: '당뇨 · 과거력',
    icon: Heart,
    fields: [
      { key: 'dm_diagnosis_age',  label: '당뇨 진단 나이', unit: '세', type: 'number',                   priority: 'recommended' },
      { key: 'hypertension',      label: '고혈압 진단',    type: 'select', options: [['0','없음'], ['1','있음']], priority: 'recommended' },
      { key: 'dm_medication',     label: '당뇨약 복용',    type: 'select', options: [['0','없음'], ['1','복용']], priority: 'recommended' },
      { key: 'insulin_medication',label: '인슐린 사용',    type: 'select', options: [['0','없음'], ['1','사용']], priority: 'recommended' },
    ],
  },
  {
    title: '소변 검사 (dipstick)',
    icon: Beaker,
    fields: [
      { key: 'he_upro',   label: '단백뇨',  type: 'number', step: '0.1', priority: 'optional', hint: '0(음성)~4' },
      { key: 'he_uglu',   label: '요당',    type: 'number', step: '0.1', priority: 'optional', hint: '0~4' },
      { key: 'he_ubld',   label: '요잠혈',  type: 'number', step: '0.1', priority: 'optional', hint: '0~4' },
      { key: 'urine_bil', label: '빌리루빈', type: 'number', step: '0.1', priority: 'optional' },
      { key: 'urine_uro', label: '우로빌리노겐', type: 'number', step: '0.1', priority: 'optional' },
      { key: 'urine_ket', label: '케톤',    type: 'number', step: '0.1', priority: 'optional' },
      { key: 'urine_nit', label: '아질산염', type: 'select', options: [['0','음성'], ['1','양성']], priority: 'optional' },
      { key: 'urine_ph',  label: 'pH',      type: 'number', step: '0.1', priority: 'optional' },
      { key: 'urine_sg',  label: '비중',    type: 'number', step: '0.001', priority: 'optional' },
    ],
  },
  {
    title: '생활 습관',
    icon: Cigarette,
    fields: [
      { key: 'smoking',     label: '현재 흡연',         type: 'select', options: [['0','비흡연'], ['1','흡연']], priority: 'optional' },
      { key: 'drinking',    label: '월 1회 이상 음주',   type: 'select', options: [['0','없음'], ['1','음주']],   priority: 'optional' },
      { key: 'exercise',    label: '주 3회 이상 유산소', type: 'select', options: [['0','없음'], ['1','운동']],   priority: 'optional' },
      { key: 'sleep_hours', label: '수면 시간',         unit: '시간', type: 'number', step: '0.5', priority: 'optional' },
    ],
  },
];

// priority 시각 토큰
const PRIORITY_STYLE = {
  required:    { mark: '*',  markColor: 'text-red-500',     label: '필수',  labelClass: 'text-red-600 bg-red-50 border-red-200' },
  recommended: { mark: '◇',  markColor: 'text-blue-500',    label: '권장',  labelClass: 'text-blue-600 bg-blue-50 border-blue-200' },
  optional:    { mark: null, markColor: 'text-gray-300',    label: '선택',  labelClass: 'text-gray-500 bg-gray-50 border-gray-200' },
};

// 백엔드 schemas.PatientBase 와 매칭되는 빈 폼 상태
const EMPTY_FORM = SECTIONS.reduce((acc, s) => {
  for (const f of s.fields) acc[f.key] = '';
  return acc;
}, {});

function FieldInput({ field, value, onChange }) {
  const baseCls = 'w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-colors';
  if (field.type === 'select') {
    return (
      <select value={value} onChange={(e) => onChange(e.target.value)} className={baseCls}>
        <option value="">{'—'}</option>
        {field.options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    );
  }
  return (
    <input
      type={field.type}
      step={field.step}
      placeholder={field.placeholder || ''}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={baseCls}
    />
  );
}

export default function ManualPatientForm() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [loadQuery, setLoadQuery] = useState('');  // 차트번호 또는 이름
  const [preloadedFrom, setPreloadedFrom] = useState(null);  // {chart_no, name} — 불러온 환자 표시
  const navigate = useNavigate();
  const toast = useToast();

  const update = (key) => (value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // 기존 환자 메타 불러오기 — 차트번호 우선, 없으면 이름 검색.
  const loadExisting = async () => {
    const q = loadQuery.trim();
    if (!q) {
      toast.info('차트번호 또는 이름을 입력하세요.');
      return;
    }
    setLoadingExisting(true);
    try {
      let patient = null;
      // 1) 차트번호 매칭 우선
      try {
        const res = await api.get(`/patients/by-chart/${encodeURIComponent(q)}`);
        patient = res.data?.data;
      } catch (e) {
        if (e.response?.status !== 404) throw e;
      }
      // 2) 이름 검색 (백엔드 search 정규화)
      if (!patient) {
        const res = await api.get(`/patients?search=${encodeURIComponent(q)}&size=10`);
        const list = res.data?.data || [];
        if (list.length === 0) {
          toast.error(`'${q}' 에 해당하는 환자를 찾을 수 없습니다.`);
          return;
        }
        if (list.length > 1) {
          toast.info(`${list.length}명 매칭. 차트번호로 다시 검색해주세요.`);
          return;
        }
        patient = list[0];
      }
      // 메타데이터만 자동 채움
      setForm((prev) => {
        const next = { ...prev };
        for (const key of PRELOAD_FIELDS) {
          const v = patient[key];
          if (v == null || v === '') continue;
          // dob 는 ISO date 문자열로 변환
          if (key === 'dob' && typeof v === 'string') {
            next[key] = v.split('T')[0];
          } else {
            next[key] = String(v);
          }
        }
        // 검사일은 오늘로 자동 (새 검사 입력 흐름)
        if (!next.exam_date) next.exam_date = new Date().toISOString().split('T')[0];
        return next;
      });
      setPreloadedFrom({ chart_no: patient.chart_no, name: patient.name });
      toast.success(`${patient.name} (${patient.chart_no}) — 기본 정보를 불러왔습니다. 새 검사 수치만 입력하세요.`);
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      toast.error('불러오기 실패: ' + detail);
      prodSafeError('ManualPatientForm.loadExisting')(e);
    } finally {
      setLoadingExisting(false);
    }
  };

  const clearPreload = () => {
    setForm(EMPTY_FORM);
    setPreloadedFrom(null);
    setLoadQuery('');
  };

  // 빈 문자열은 null 로 / 숫자는 number 로 / select 의 0,1 은 int 로 변환
  const buildPayload = () => {
    const out = {};
    for (const section of SECTIONS) {
      for (const f of section.fields) {
        const v = form[f.key];
        if (v === '' || v == null) {
          out[f.key] = null;
          continue;
        }
        if (f.type === 'number') {
          const n = parseFloat(v);
          out[f.key] = Number.isFinite(n) ? n : null;
        } else if (f.type === 'select' && f.options.every(([opt]) => opt === '0' || opt === '1')) {
          out[f.key] = parseInt(v, 10);
        } else {
          out[f.key] = v;
        }
      }
    }
    return out;
  };

  // 필수 항목 누락 시 — 정확한 라벨로 안내.
  const REQUIRED_FIELDS = SECTIONS.flatMap(s =>
    s.fields.filter(f => f.priority === 'required')
  );

  const validate = () => {
    const missing = REQUIRED_FIELDS.filter(f => {
      const v = form[f.key];
      return v === '' || v == null;
    });
    if (missing.length === 0) return null;
    if (missing.length === 1) {
      return `필수 항목을 입력해주세요: ${missing[0].label}`;
    }
    const names = missing.slice(0, 5).map(f => f.label).join(', ');
    const more = missing.length > 5 ? ` 외 ${missing.length - 5}개` : '';
    return `필수 항목 ${missing.length}개를 입력해주세요: ${names}${more}`;
  };

  // 진척도 — 필수 항목 채워진 비율 (UI 상단 progress 표시)
  const requiredFilled = REQUIRED_FIELDS.filter(f => {
    const v = form[f.key];
    return v !== '' && v != null;
  }).length;
  const requiredTotal = REQUIRED_FIELDS.length;
  const requiredPct = requiredTotal > 0 ? Math.round((requiredFilled / requiredTotal) * 100) : 100;

  const submit = async (e) => {
    e?.preventDefault?.();
    setError(null);
    const v = validate();
    if (v) {
      setError(v);
      toast.error(v, { title: '입력 확인' });
      return;
    }
    setSubmitting(true);
    try {
      const payload = buildPayload();
      const res = await api.post('/patients', payload);
      const created = res.data?.data;
      toast.success(`${created?.name || '환자'}님이 등록되었습니다.`, { title: '등록 완료' });
      const id = created?.id;
      if (id) {
        navigate(`/dashboard/${id}`);
      } else {
        navigate('/patients');
      }
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setError(String(detail));
      toast.error(String(detail), { title: '등록 실패' });
      prodSafeError('ManualPatientForm.submit')(err);
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setPreloadedFrom(null);
    setLoadQuery('');
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      {/* 기존 환자 불러오기 (v2.1.2) */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <UserCheck size={16} className="text-blue-600" />
          <h3 className="text-sm font-bold text-gray-800">기존 환자 정보 불러오기</h3>
          <span className="text-[10px] text-gray-500">차트번호 또는 이름으로 기본 정보를 불러와 새 검사 수치만 입력</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={loadQuery}
            onChange={(e) => setLoadQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); loadExisting(); } }}
            placeholder="차트번호 (예: CN-2026-0001) 또는 환자 이름"
            className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-blue-400"
          />
          <button
            type="button"
            onClick={loadExisting}
            disabled={loadingExisting || !loadQuery.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Search size={12} />
            {loadingExisting ? '불러오는 중...' : '불러오기'}
          </button>
        </div>
        {preloadedFrom && (
          <div className="mt-2 text-[11px] text-blue-700 flex items-center gap-2">
            <span>✓ <b>{preloadedFrom.name}</b> ({preloadedFrom.chart_no}) 정보가 불러와졌습니다 — 새 검사 수치만 입력 후 저장하세요.</span>
            <button type="button" onClick={clearPreload} className="text-[10px] text-gray-500 underline hover:text-gray-700">초기화</button>
          </div>
        )}
      </div>

      {/* 범례 + 진척도 */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px]">
            <span className="font-semibold text-gray-700">표시 안내</span>
            <span className="inline-flex items-center gap-1">
              <span className="text-red-500 font-bold">*</span>
              <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-semibold ${PRIORITY_STYLE.required.labelClass}`}>필수</span>
              <span className="text-gray-500">— ML 예측 정확도 핵심</span>
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="text-blue-500 font-bold">◇</span>
              <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-semibold ${PRIORITY_STYLE.recommended.labelClass}`}>권장</span>
              <span className="text-gray-500">— 있으면 정확도 향상</span>
            </span>
            <span className="inline-flex items-center gap-1">
              <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-semibold ${PRIORITY_STYLE.optional.labelClass}`}>선택</span>
              <span className="text-gray-500">— 보조 지표</span>
            </span>
          </div>
          <div className="flex items-center gap-2 min-w-[200px]">
            <span className="text-[11px] font-semibold text-gray-700">필수 입력</span>
            <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-2 rounded-full transition-all ${requiredPct === 100 ? 'bg-emerald-500' : 'bg-red-400'}`}
                style={{ width: `${requiredPct}%` }}
              />
            </div>
            <span className={`text-[11px] font-bold tabular-nums ${requiredPct === 100 ? 'text-emerald-600' : 'text-red-600'}`}>
              {requiredFilled}/{requiredTotal}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2 text-sm text-red-700">
          <AlertCircle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {SECTIONS.map((section) => {
          const Icon = section.icon;
          const sectionReqCount = section.fields.filter(f => f.priority === 'required').length;
          return (
            <div key={section.title} className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
              <h3 className="text-sm font-bold text-gray-800 flex items-center gap-2 mb-4">
                <Icon size={14} className="text-accent" />
                {section.title}
                {sectionReqCount > 0 && (
                  <span className="ml-auto text-[10px] font-medium text-red-500">필수 {sectionReqCount}개</span>
                )}
              </h3>
              <div className="grid grid-cols-2 gap-x-3 gap-y-3">
                {section.fields.map((f) => {
                  const style = PRIORITY_STYLE[f.priority] || PRIORITY_STYLE.optional;
                  return (
                    <div key={f.key} className={f.type === 'date' || f.label.length > 10 ? 'col-span-2 sm:col-span-1' : ''}>
                      <label className="block text-[11px] font-medium text-gray-600 mb-1">
                        {style.mark && <span className={`${style.markColor} font-bold mr-0.5`}>{style.mark}</span>}
                        {f.label}
                        {f.unit && <span className="text-gray-400 ml-1 font-normal">({f.unit})</span>}
                      </label>
                      <FieldInput field={f} value={form[f.key]} onChange={update(f.key)} />
                      {f.hint && <p className="text-[10px] text-gray-400 mt-1">{f.hint}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="sticky bottom-0 bg-gradient-to-t from-white via-white to-transparent pt-4 pb-2 flex items-center gap-3 z-10">
        <button
          type="button"
          onClick={reset}
          disabled={submitting}
          className="px-5 py-3 border border-gray-200 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 disabled:opacity-50"
        >
          초기화
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="flex-1 bg-accent text-white py-3 rounded-xl text-sm font-bold hover:bg-accent-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center justify-center gap-2"
        >
          {submitting ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              저장 중...
            </>
          ) : (
            <>
              <Save size={16} />
              환자 등록 및 프로필 생성
            </>
          )}
        </button>
      </div>

      <p className="text-[11px] text-gray-400 text-center pt-2">
        나이 · BMI · eGFR · HOMA-IR · TyG · 맥압 등은 입력값으로부터 자동 계산되어 저장됩니다.
      </p>
    </form>
  );
}
