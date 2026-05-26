import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Save, AlertCircle } from 'lucide-react';
import api from '../api/client';

/**
 * 환자 데이터 수정 모달.
 * CSV와 동일한 필드 구조로 전체 항목을 한번에 편집한다.
 * 저장 시 PATCH /patients/{id} 호출.
 */

// v2 스키마 — 병원 수집 변수 기준
const DIP_OPTS = [
  { v: 1, l: '1 (음성)' },
  { v: 2, l: '2 (±)' },
  { v: 3, l: '3 (1+)' },
  { v: 4, l: '4 (2+)' },
  { v: 5, l: '5 (3+)' },
  { v: 6, l: '6 (4+)' },
];

const SECTIONS = [
  {
    title: '메타데이터',
    fields: [
      { key: 'name', label: '이름', type: 'text' },
      { key: 'chart_no', label: '차트번호', type: 'text' },
      { key: 'phone', label: '연락처', type: 'text', placeholder: '010-0000-0000' },
      { key: 'exam_date', label: '최근 검사일', type: 'date' },
      { key: 'dob', label: '생년월일', type: 'date' },
    ],
  },
  {
    title: '인구통계 / 당뇨',
    fields: [
      { key: 'age', label: '나이', type: 'number', unit: '세' },
      { key: 'sex', label: '성별', type: 'select', options: [{ v: 'M', l: '남' }, { v: 'F', l: '여' }] },
      { key: 'dm_diagnosis_age', label: '당뇨 진단 연령', type: 'number', unit: '세' },
      { key: 'dm_duration', label: '당뇨 이환기간', type: 'number', unit: '년' },
      { key: 'dm_medication', label: '당뇨약 복용', type: 'select', options: [{ v: 0, l: '복용 안 함' }, { v: 1, l: '복용' }] },
      { key: 'insulin_medication', label: '인슐린 투약', type: 'select', options: [{ v: 0, l: '투약 안 함' }, { v: 1, l: '투약' }] },
    ],
  },
  {
    title: '혈당 / 인슐린',
    fields: [
      { key: 'hba1c', label: '당화혈색소 HbA1c', type: 'number', step: '0.1', unit: '%' },
      { key: 'c_peptide', label: 'C-peptide', type: 'number', step: '0.1', unit: 'ng/mL' },
      { key: 'fbg', label: '공복혈당', type: 'number', unit: 'mg/dL' },
      { key: 'he_insulin', label: '인슐린 (선택)', type: 'number', step: '0.1', unit: 'μU/mL' },
    ],
  },
  {
    title: '간 기능',
    fields: [
      { key: 'ggt', label: 'GGT (참고)', type: 'number', unit: 'U/L' },
      { key: 'alt', label: 'ALT', type: 'number', unit: 'U/L' },
      { key: 'ast', label: 'AST', type: 'number', unit: 'U/L' },
    ],
  },
  {
    title: '신장 기능',
    fields: [
      { key: 'cr', label: '크레아티닌 Cr', type: 'number', step: '0.01', unit: 'mg/dL' },
    ],
  },
  {
    title: '지질 / 혈압',
    fields: [
      { key: 'total_cholesterol', label: '총콜레스테롤', type: 'number', unit: 'mg/dL' },
      { key: 'triglycerides', label: '중성지방', type: 'number', unit: 'mg/dL' },
      { key: 'hdl', label: 'HDL', type: 'number', unit: 'mg/dL' },
      { key: 'ldl', label: 'LDL (실측)', type: 'number', unit: 'mg/dL' },
      { key: 'sbp', label: '수축기혈압', type: 'number', unit: 'mmHg' },
      { key: 'dbp', label: '이완기혈압', type: 'number', unit: 'mmHg' },
      { key: 'hypertension', label: '고혈압 진단', type: 'select', options: [{ v: 0, l: '없음' }, { v: 1, l: '있음' }] },
    ],
  },
  {
    title: '신체 계측',
    fields: [
      { key: 'bmi', label: 'BMI', type: 'number', step: '0.1', unit: 'kg/m²' },
      { key: 'height', label: '신장', type: 'number', step: '0.1', unit: 'cm' },
      { key: 'weight', label: '체중', type: 'number', step: '0.1', unit: 'kg' },
      { key: 'visceral_fat', label: '내장지방 레벨 (참고)', type: 'number', step: '0.1', unit: '' },
    ],
  },
  {
    title: '소변 검사 (dipstick)',
    fields: [
      { key: 'he_upro', label: '요단백', type: 'select', options: DIP_OPTS },
      { key: 'he_uglu', label: '요당', type: 'select', options: DIP_OPTS },
      { key: 'he_ubld', label: '요잠혈', type: 'select', options: DIP_OPTS },
      { key: 'urine_bil', label: '요빌리루빈', type: 'select', options: DIP_OPTS.slice(0, 5) },
      { key: 'urine_uro', label: '요우로빌리노겐', type: 'select', options: DIP_OPTS.slice(0, 5) },
      { key: 'urine_ket', label: '요케톤', type: 'select', options: DIP_OPTS.slice(0, 5) },
      { key: 'urine_nit', label: '요아질산염', type: 'select', options: [{ v: 0, l: '음성' }, { v: 1, l: '양성' }] },
      { key: 'urine_ph', label: '요 pH', type: 'number', step: '0.1', unit: '' },
      { key: 'urine_sg', label: '요비중', type: 'number', step: '0.001', unit: '' },
    ],
  },
  {
    title: '생활습관',
    fields: [
      { key: 'smoking', label: '흡연', type: 'select', options: [{ v: 0, l: '비흡연' }, { v: 1, l: '흡연' }] },
      { key: 'drinking', label: '음주', type: 'select', options: [{ v: 0, l: '비음주' }, { v: 1, l: '음주' }] },
      { key: 'exercise', label: '규칙적 운동', type: 'select', options: [{ v: 0, l: '안함' }, { v: 1, l: '주 150분 이상' }] },
      { key: 'sleep_hours', label: '일평균 수면시간', type: 'number', step: '0.5', unit: '시간' },
    ],
  },
];

function formatDate(value) {
  if (!value) return '';
  if (typeof value === 'string') return value.slice(0, 10);
  try { return new Date(value).toISOString().slice(0, 10); } catch { return ''; }
}

export default function EditPatientModal({ patient, onClose, onSaved }) {
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const dialogRef = useRef(null);
  const closeBtnRef = useRef(null);
  const previousFocus = useRef(null);

  useEffect(() => {
    if (!patient) return;
    const initial = {};
    SECTIONS.forEach((s) => {
      s.fields.forEach((f) => {
        let v = patient[f.key];
        if (f.type === 'date') v = formatDate(v);
        initial[f.key] = v ?? '';
      });
    });
    setForm(initial);
  }, [patient]);

  // 포커스 트랩 + Esc + body 스크롤락
  useEffect(() => {
    if (!patient) return;
    previousFocus.current = document.activeElement;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    setTimeout(() => closeBtnRef.current?.focus(), 0);
    return () => {
      document.body.style.overflow = prevOverflow;
      previousFocus.current?.focus?.();
    };
  }, [patient]);

  const handleKey = useCallback((e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose?.();
      return;
    }
    if (e.key !== 'Tab') return;
    const root = dialogRef.current;
    if (!root) return;
    const focusable = root.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, [onClose]);

  if (!patient) return null;

  const setField = (key, val) => setForm((prev) => ({ ...prev, [key]: val }));

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      // 빈 문자열은 null 처리, select number 변환
      const payload = {};
      Object.entries(form).forEach(([k, v]) => {
        if (v === '' || v === null || v === undefined) {
          payload[k] = null;
        } else {
          payload[k] = v;
        }
      });
      const res = await api.patch(`/patients/${patient.id}`, payload);
      onSaved?.(res.data?.data);
      onClose?.();
    } catch (e) {
      setError(e.response?.data?.detail || e.message || '저장 실패');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
      onKeyDown={handleKey}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-patient-title"
        aria-describedby="edit-patient-desc"
        className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 id="edit-patient-title" className="text-lg font-bold text-gray-900">{patient.name} {'\uD658\uC790 \uB370\uC774\uD130 \uC218\uC815'}</h2>
            <p id="edit-patient-desc" className="text-xs text-gray-500 mt-0.5">{'CSV \uAD6C\uC870\uC640 \uB3D9\uC77C\uD55C \uD56D\uBAA9\uC744 \uC9C1\uC811 \uD3B8\uC9D1\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.'}</p>
          </div>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            aria-label={'\uB2EB\uAE30'}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {error && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg p-3">
              <AlertCircle size={14} /> {error}
            </div>
          )}
          {SECTIONS.map((section) => (
            <div key={section.title}>
              <h3 className="text-[11px] font-bold uppercase tracking-wider text-indigo-600 mb-2">{section.title}</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {section.fields.map((f) => {
                  const val = form[f.key] ?? '';
                  return (
                    <label key={f.key} className="block">
                      <span className="text-[11px] font-medium text-gray-600 mb-1 flex items-center justify-between">
                        {f.label}
                        {f.unit && <span className="text-gray-400">{f.unit}</span>}
                      </span>
                      {f.type === 'select' ? (
                        <select
                          value={val}
                          onChange={(e) => setField(f.key, e.target.value === '' ? '' : Number(e.target.value))}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
                        >
                          <option value="">{'\uC120\uD0DD'}</option>
                          {f.options.map((o) => (
                            <option key={o.v} value={o.v}>{o.l}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={f.type}
                          step={f.step}
                          placeholder={f.placeholder}
                          value={val}
                          onChange={(e) => {
                            const raw = e.target.value;
                            if (f.type === 'number') {
                              setField(f.key, raw === '' ? '' : Number(raw));
                            } else {
                              setField(f.key, raw);
                            }
                          }}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent"
                        />
                      )}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            {'\uCDE8\uC18C'}
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="px-5 py-2 bg-accent text-white text-sm font-semibold rounded-lg hover:bg-accent-dark disabled:opacity-50 flex items-center gap-2"
          >
            <Save size={14} />
            {saving ? '\uC800\uC7A5 \uC911...' : '\uC800\uC7A5'}
          </button>
        </div>
      </div>
    </div>
  );
}
