import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, CheckCircle, AlertTriangle, AlertCircle, Info, X, Database, Sparkles, ArrowRight, FileSpreadsheet, UserPlus } from 'lucide-react';
import api from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { prodSafeError } from '../theme';
import ManualPatientForm from '../components/ManualPatientForm';

// 업로드 성공 후 자동 이동 대기 시간 (ms)
const AUTO_REDIRECT_MS = 1500;

// CSV 검증 한계 (J3)
const MAX_CSV_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB (v2.2.1: 엑셀 지원 + 상향)
const ACCEPTED_MIME = ['text/csv', 'application/vnd.ms-excel', 'application/csv', 'text/plain', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/octet-stream', '']; // 일부 브라우저는 빈 문자열

function validateCsvFile(f) {
  if (!f) return '\uD30C\uC77C\uC744 \uC120\uD0DD\uD558\uC138\uC694.';
  const lower = f.name.toLowerCase();
  if (!lower.endsWith('.csv') && !lower.endsWith('.xlsx')) return 'CSV \uD30C\uC77C\uB9CC \uC5C5\uB85C\uB4DC \uAC00\uB2A5\uD569\uB2C8\uB2E4 (.csv \uD655\uC7A5\uC790).';
  if (f.size > MAX_CSV_SIZE_BYTES) {
    const mb = (f.size / 1024 / 1024).toFixed(1);
    return `\uD30C\uC77C\uC774 \uB108\uBB34 \uD07D\uB2C8\uB2E4 (${mb}MB). \uCD5C\uB300 10MB \uAE4C\uC9C0 \uC9C0\uC6D0\uB429\uB2C8\uB2E4.`;
  }
  if (f.size === 0) return '\uBE48 \uD30C\uC77C\uC785\uB2C8\uB2E4.';
  // MIME 체크는 보조 수단 (일부 OS/브라우저에서 type 이 비어있음)
  if (f.type && !ACCEPTED_MIME.includes(f.type) && !f.type.includes('csv') && !f.type.includes('spreadsheet')) {
    return `\uC9C0\uC6D0\uB418\uC9C0 \uC54A\uB294 \uD30C\uC77C \uD615\uC2DD\uC785\uB2C8\uB2E4 (${f.type}). CSV \uB9CC \uC5C5\uB85C\uB4DC \uAC00\uB2A5\uD569\uB2C8\uB2E4.`;
  }
  return null;
}

// v2.2.2 fix: \uC5D1\uC140 \uC5EC\uBD80 \uD310\uBCC4 \uD5EC\uD37C. (v2.2.1 \uC5D1\uC140 \uC9C0\uC6D0 \uCD94\uAC00 \uC2DC \uD638\uCD9C\uB9CC \uD558\uACE0 \uC815\uC758\uAC00 \uBE60\uC838
//   handleFile \uC774 ReferenceError \uB85C \uC8FD\uC5B4 '\uD30C\uC77C\uC774 \uC548 \uB4E4\uC5B4\uAC00\uB294' \uBC84\uADF8\uAC00 \uC788\uC5C8\uC74C)
function isXlsxFile(f) {
  return !!f && f.name.toLowerCase().endsWith('.xlsx');
}

// \uC5D0\uB7EC(\uBB38\uC790\uC5F4/Error/\uAC1D\uCCB4/\uBC30\uC5F4/FastAPI detail)\uB97C \uD56D\uC0C1 \uC77D\uC744 \uC218 \uC788\uB294 \uBB38\uC790\uC5F4\uB85C \uBCC0\uD658.
//   "[object Object]" \uB85C \uD45C\uC2DC\uB418\uB358 \uBB38\uC81C \uBC29\uC9C0.
function errToText(e) {
  if (e == null) return '\uC54C \uC218 \uC5C6\uB294 \uC624\uB958';
  if (typeof e === 'string') return e;
  if (Array.isArray(e)) return e.map(errToText).filter(Boolean).join(', ');
  if (typeof e === 'object') {
    return e.msg || e.message || e.detail || e.reason || e.error || JSON.stringify(e);
  }
  return String(e);
}

export default function Home() {
  const [mode, setMode] = useState('csv'); // 'csv' | 'manual'
  const [file, setFile] = useState(null);
  const [mapping, setMapping] = useState([]);
  const [feedback, setFeedback] = useState({ errors: [], warnings: [], successes: [] });
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const [createdCount, setCreatedCount] = useState(0);
  const [updatedCount, setUpdatedCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);
  const [visitsAdded, setVisitsAdded] = useState(0);
  const [redirectIn, setRedirectIn] = useState(null);
  const [redirectTo, setRedirectTo] = useState('/patients');
  const [redirectLabel, setRedirectLabel] = useState('환자 목록');
  const [statusMessage, setStatusMessage] = useState(''); // aria-live 용 (D8)
  const inputRef = useRef(null);
  const dropZoneRef = useRef(null);
  const redirectTimerRef = useRef(null);
  const countdownIntervalRef = useRef(null);
  const navigate = useNavigate();
  const toast = useToast();

  // 언마운트 시 타이머 정리
  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
      if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
    };
  }, []);

  const cancelRedirect = () => {
    if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
    if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
    redirectTimerRef.current = null;
    countdownIntervalRef.current = null;
    setRedirectIn(null);
  };

  const resetAll = () => {
    cancelRedirect();
    setFile(null);
    setMapping([]);
    setFeedback({ errors: [], warnings: [], successes: [] });
    setHasSubmitted(false);
    setCreatedCount(0);
    setUpdatedCount(0);
    setSkippedCount(0);
    setVisitsAdded(0);
    setStatusMessage('\uD30C\uC77C \uC120\uD0DD \uCDE8\uC18C\uB428');
  };

  const handleFile = (f) => {
    const err = validateCsvFile(f);
    if (err) {
      setFeedback({ errors: [err], warnings: [], successes: [] });
      setStatusMessage(err);
      return;
    }
    setFile(f);
    setHasSubmitted(false);
    setCreatedCount(0);
    setFeedback({ errors: [], warnings: [], successes: [] });
    setStatusMessage(`\uD30C\uC77C \uC120\uD0DD\uB428: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`);
    // v2.2.1: \uC5D1\uC140(.xlsx)\uC740 \uBC14\uC774\uB108\uB9AC\uB77C \uBE0C\uB77C\uC6B0\uC800 \uBBF8\uB9AC\uBCF4\uAE30 \uBD88\uAC00 \u2192 \uC2A4\uD0B5, \uC11C\uBC84 \uB9E4\uD551\uC774 \uAD8C\uC704.
    // v2.2.2: 확장자가 .csv 라도 내용이 엑셀(PK/zip)이면 텍스트 미리보기가 깨지므로 내용으로 판별.
    const reader = new FileReader();
    reader.onload = (e) => {
      const buf = new Uint8Array(e.target.result || new ArrayBuffer(0));
      const isZipXlsx = buf.length >= 2 && buf[0] === 0x50 && buf[1] === 0x4B; // 'PK' = xlsx/zip
      if (isXlsxFile(f) || isZipXlsx) {
        // 엑셀(.xlsx 또는 .csv 로 위장한 엑셀) → 브라우저 미리보기 불가, 서버가 매핑.
        setMapping([]);
        return;
      }
      const firstLine = new TextDecoder('utf-8').decode(buf).split('\n')[0] || '';
      const cols = firstLine.replace(/\r/g, '').replace(/^\uFEFF/, '').split(',').map((s) => s.trim()).filter(Boolean);
      setMapping(cols.map((c) => ({ csv_column: c, db_field: null, status: 'pending', kind: null })));
      setStatusMessage(`\uD30C\uC77C \uC900\uBE44 \uC644\uB8CC. ${cols.length}\uAC1C \uCEEC\uB7FC \uAC10\uC9C0\uB428.`);
    };
    reader.readAsArrayBuffer(f.slice(0, 4096));
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  const onDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  const onSelect = (e) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  // D7: 키보드 접근성 — Enter/Space 로 드롭존 활성화
  const onDropZoneKey = (e) => {
    if (file) return; // 이미 파일이 선택됐으면 무시
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  const submit = async () => {
    if (!file) return;
    cancelRedirect();
    setUploading(true);
    setHasSubmitted(true);
    setStatusMessage('\uC5C5\uB85C\uB4DC \uC2DC\uC791...');
    try {
      const formData = new FormData();
      formData.append('file', file);
      // v2.1.11: Content-Type 을 수동 지정하지 않는다.
      // axios/브라우저가 multipart boundary 를 자동으로 넣게 둬야 서버 파싱이 안정적.
      // 대용량 CSV 대비 업로드 타임아웃을 넉넉히 (기본 10초 → 120초).
      const res = await api.post('/upload/csv', formData, { timeout: 120000 });
      const data = res.data.data || {};
      const validation = data.validation || {};
      setFeedback({
        errors: validation.errors || [],
        warnings: validation.warnings || [],
        successes: validation.successes || [],
      });
      if (Array.isArray(data.mapping_preview)) {
        setMapping(data.mapping_preview);
      }
      const count = data.created_count || 0;
      const updated = data.updated_count || 0;
      const skipped = data.skipped_count || 0;
      const visits = data.visits_added || 0;
      setCreatedCount(count);
      setUpdatedCount(updated);
      setSkippedCount(skipped);
      setVisitsAdded(visits);

      // 중복 chart_no 로 스킵된 행은 경고로 노출
      if (skipped > 0 && Array.isArray(data.skipped)) {
        const skipMsgs = data.skipped.map((s) => `행 ${s.row} (${s.chart_no}): ${s.reason}`);
        setFeedback((prev) => ({
          ...prev,
          warnings: [...(prev.warnings || []), ...skipMsgs],
        }));
      }

      const hasErrors = (validation.errors || []).length > 0;
      const savedAny = count > 0 || updated > 0 || visits > 0;

      if (!hasErrors && savedAny) {
        const parts = [];
        if (count > 0) parts.push(`신규 ${count}명`);
        if (updated > 0) parts.push(`업데이트 ${updated}명`);
        if (visits > 0) parts.push(`검사 ${visits}건`);
        if (skipped > 0) parts.push(`건너뜀 ${skipped}건`);
        toast.success(parts.join(' · '), { title: '업로드 완료' });
        setStatusMessage(`\uC5C5\uB85C\uB4DC \uC131\uACF5: ${parts.join(', ')}`);

        let target = '/patients';
        let label = '환자 목록';
        if (data.is_single_patient && data.last_patient_id) {
          target = `/dashboard/${data.last_patient_id}`;
          label = '환자 대시보드';
        }
        setRedirectTo(target);
        setRedirectLabel(label);

        setRedirectIn(Math.ceil(AUTO_REDIRECT_MS / 1000));
        let remaining = Math.ceil(AUTO_REDIRECT_MS / 1000);
        countdownIntervalRef.current = setInterval(() => {
          remaining -= 1;
          setRedirectIn(remaining > 0 ? remaining : 0);
        }, 1000);
        redirectTimerRef.current = setTimeout(() => {
          cancelRedirect();
          navigate(target);
        }, AUTO_REDIRECT_MS);
      } else if (hasErrors) {
        const msg = `${validation.errors.length}\uAC1C\uC758 \uC624\uB958\uB97C \uD574\uACB0\uD574\uC57C \uD569\uB2C8\uB2E4.`;
        toast.error(msg, { title: '업로드 실패' });
        setStatusMessage(msg);
      } else if (!savedAny && skipped > 0) {
        const msg = `\uBAA8\uB4E0 \uD589(${skipped}\uAC74)\uC774 \uC911\uBCF5\uC73C\uB85C \uAC74\uB108\uB6F0\uC5B4\uC84C\uC2B5\uB2C8\uB2E4.`;
        toast.info(msg, { title: '신규 등록 없음' });
        setStatusMessage(msg);
      }
    } catch (err) {
      // FastAPI 422 는 detail 이 객체/배열이라 String() 하면 "[object Object]" → errToText 로 변환
      const detail = errToText(err.response?.data?.detail ?? err.message ?? err);
      setFeedback({ errors: [detail], warnings: [], successes: [] });
      toast.error(detail, { title: '업로드 오류' });
      setStatusMessage(`\uC5C5\uB85C\uB4DC \uC624\uB958: ${detail}`);
      prodSafeError('Home.upload')(err);
    } finally {
      setUploading(false);
    }
  };

  const goNow = () => {
    cancelRedirect();
    navigate(redirectTo);
  };

  const hasMapping = mapping.length > 0;
  const mappedCount = mapping.filter((m) => m.status === 'mapped' || m.db_field).length;
  const metaCount = mapping.filter((m) => m.kind === '메타').length;
  const varCount = mapping.filter((m) => m.kind === '변수').length;

  return (
    <div className="flex flex-col gap-4 w-full flex-1 min-h-0">
      {/* aria-live 영역: 스크린리더용 비가시 상태 알림 (D8) */}
      <div role="status" aria-live="polite" className="sr-only">
        {statusMessage}
      </div>

      {/* Header compact */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">{'\uD658\uC790 \uB370\uC774\uD130 \uC5C5\uB85C\uB4DC'}</h1>
        <p className="text-xs text-gray-500 mt-0.5">
          {'CSV \uD30C\uC77C \uD558\uB098\uB85C \uBA54\uD0C0\uC815\uBCF4 + ML \uB3C5\uB9BD\uBCC0\uC218\uB97C \uD568\uAED8 \uB4F1\uB85D\uD569\uB2C8\uB2E4.'}
        </p>
      </div>

      {/* 모드 탭 */}
      <div className="flex items-center gap-2 -mt-2">
        <button
          onClick={() => setMode('csv')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            mode === 'csv'
              ? 'bg-accent text-white shadow-sm'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
        >
          <FileSpreadsheet size={14} />
          {'CSV 일괄 업로드'}
        </button>
        <button
          onClick={() => setMode('manual')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            mode === 'manual'
              ? 'bg-accent text-white shadow-sm'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
          }`}
        >
          <UserPlus size={14} />
          {'한 명 직접 입력'}
        </button>
      </div>

      {mode === 'manual' && <ManualPatientForm />}

      {/* Main area: huge drop zone + side panel */}
      {mode === 'csv' && (
      <div className="grid grid-cols-12 gap-4 flex-1 min-h-0">
        {/* LEFT: big drop zone takes 7/12 */}
        <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">
          <div
            ref={dropZoneRef}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onClick={() => !file && inputRef.current?.click()}
            onKeyDown={onDropZoneKey}
            role="button"
            tabIndex={file ? -1 : 0}
            aria-label={file
              ? `\uC120\uD0DD\uB41C \uD30C\uC77C: ${file.name}`
              : 'CSV \uD30C\uC77C\uC744 \uC774 \uC601\uC5ED\uC5D0 \uB4DC\uB86D\uD558\uAC70\uB098 Enter/Space \uD0A4\uB97C \uB20C\uB7EC \uD30C\uC77C\uC744 \uC120\uD0DD\uD558\uC138\uC694'}
            className={`flex-1 min-h-[360px] rounded-2xl border-2 border-dashed p-8 flex flex-col items-center justify-center text-center transition-all cursor-pointer focus:outline-none focus-visible:ring-4 focus-visible:ring-accent/30 focus-visible:border-accent ${
              dragging
                ? 'border-accent bg-accent-soft/40 scale-[1.01]'
                : file
                ? 'border-emerald-300 bg-emerald-50/40'
                : 'border-gray-300 bg-white hover:border-accent hover:bg-accent-soft/20'
            }`}
          >
            {!file ? (
              <>
                <div className="w-24 h-24 rounded-full bg-accent-soft flex items-center justify-center mb-5 shadow-sm" aria-hidden="true">
                  <Upload size={42} className="text-accent" strokeWidth={1.6} />
                </div>
                <h3 className="text-lg font-bold text-gray-900 mb-2">
                  {'CSV \uD30C\uC77C\uC744 \uC5EC\uAE30\uC5D0 \uB4DC\uB86D\uD558\uC138\uC694'}
                </h3>
                <p className="text-sm text-gray-500 mb-6">
                  {'\uB610\uB294 \uC544\uB798 \uBC84\uD2BC\uC744 \uB20C\uB7EC \uD30C\uC77C\uC744 \uC9C1\uC811 \uC120\uD0DD\uD558\uACE0, \uD0A4\uBCF4\uB4DC \uC0AC\uC6A9 \uC2DC '}
                  <kbd className="px-1 py-0.5 text-[10px] bg-gray-100 border border-gray-200 rounded font-mono">Enter</kbd>
                  {' \uB610\uB294 '}
                  <kbd className="px-1 py-0.5 text-[10px] bg-gray-100 border border-gray-200 rounded font-mono">Space</kbd>
                  {'.'}
                  <br />
                  <span className="text-xs text-gray-400">{'\uCD5C\uB300 10MB \u00B7 UTF-8 \uC778\uCF54\uB529 \u00B7 \uCB9D\uAD00\uB7FC: name, chart_no, phone, exam_date + ML \uBCC0\uC218'}</span>
                </p>
                <button
                  onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
                  className="bg-accent text-white px-8 py-3 rounded-xl text-sm font-semibold hover:bg-accent-dark transition-colors shadow-sm"
                >
                  {'\uD30C\uC77C \uC120\uD0DD'}
                </button>
              </>
            ) : (
              <>
                <div className="w-20 h-20 rounded-full bg-emerald-100 flex items-center justify-center mb-4 shadow-sm" aria-hidden="true">
                  <FileText size={36} className="text-emerald-600" strokeWidth={1.6} />
                </div>
                <p className="text-base font-bold text-gray-900">{file.name}</p>
                <p className="text-xs text-gray-500 mt-1 mb-4">
                  {(file.size / 1024).toFixed(1)} KB \u00B7 {mapping.length}{'\uAC1C \uCEEC\uB7FC \uAC10\uC9C0\uB428'}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
                    className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-50"
                  >
                    {'\uB2E4\uB978 \uD30C\uC77C \uC120\uD0DD'}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); resetAll(); }}
                    className="px-4 py-2 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-50 flex items-center gap-1"
                  >
                    <X size={12} /> {'\uCDE8\uC18C'}
                  </button>
                </div>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={onSelect}
              aria-hidden="true"
              tabIndex={-1}
            />
          </div>

          {/* Mapping preview compact */}
          {hasMapping && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-xs font-bold text-gray-800 flex items-center gap-2">
                  <Database size={14} className="text-accent" aria-hidden="true" />
                  {'\uB9E4\uD551 \uBBF8\uB9AC\uBCF4\uAE30'}
                </h3>
                <span className="text-[11px] text-gray-500">
                  {mapping.length}{'\uAC1C \uC870 / \uB9E4\uD551 '}{mappedCount}{'\uAC1C '}
                  {hasSubmitted && metaCount > 0 && <span className="text-accent">({'\uBA54\uD0C0 '}{metaCount}\u00B7{'\uBCC0\uC218 '}{varCount})</span>}
                </span>
              </div>
              <div className="max-h-[180px] overflow-y-auto">
                <table className="w-full text-[11px]">
                  <thead className="bg-gray-50 border-b border-gray-100 sticky top-0">
                    <tr>
                      <th className="text-left px-4 py-1.5 font-semibold text-gray-500 uppercase">CSV</th>
                      <th className="text-left px-4 py-1.5 font-semibold text-gray-500 uppercase">DB</th>
                      <th className="text-left px-4 py-1.5 font-semibold text-gray-500 uppercase">{'\uBD84\uB958'}</th>
                      <th className="text-left px-4 py-1.5 font-semibold text-gray-500 uppercase">{'\uC0C1\uD0DC'}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {mapping.map((m, i) => (
                      <tr key={i}>
                        <td className="px-4 py-1 text-gray-800 font-mono">{m.csv_column}</td>
                        <td className="px-4 py-1 text-gray-600 font-mono">{m.db_field || '\u2014'}</td>
                        <td className="px-4 py-1">
                          {m.kind === '메타' && <span className="px-1.5 py-0.5 rounded bg-accent-soft text-accent text-[10px]">{'\uBA54\uD0C0'}</span>}
                          {m.kind === '변수' && <span className="px-1.5 py-0.5 rounded bg-sky-100 text-sky-700 text-[10px]">{'\uBCC0\uC218'}</span>}
                        </td>
                        <td className="px-4 py-1">
                          {m.status === 'mapped' && <span className="text-green-600 flex items-center gap-1"><CheckCircle size={11} aria-hidden="true" />{'\uC131\uACF5'}</span>}
                          {m.status === 'unmapped' && <span className="text-orange-600 flex items-center gap-1"><AlertTriangle size={11} aria-hidden="true" />{'\uBBF8\uB9E4\uD551'}</span>}
                          {m.status === 'pending' && <span className="text-gray-400">{'\uB300\uAE30'}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT: validation + submit */}
        <div className="col-span-12 lg:col-span-5 flex flex-col gap-4">
          <div className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm flex-1 min-h-[300px] flex flex-col">
            <h3 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
              <Sparkles size={14} className="text-accent" aria-hidden="true" />
              {'\uC720\uD6A8\uC131 \uAC80\uC0AC \uACB0\uACFC'}
            </h3>

            {!hasSubmitted && !file && (
              <div className="flex-1 flex flex-col items-center justify-center text-center">
                <Info size={28} className="text-gray-300 mb-3" aria-hidden="true" />
                <p className="text-xs text-gray-400">{'\uD30C\uC77C\uC744 \uC120\uD0DD\uD558\uACE0 \uC5C5\uB85C\uB4DC\uD558\uBA74 \uAC80\uC0AC \uACB0\uACFC\uAC00 \uD45C\uC2DC\uB429\uB2C8\uB2E4.'}</p>
              </div>
            )}

            {!hasSubmitted && file && (
              <div className="flex-1 flex flex-col items-center justify-center text-center">
                <CheckCircle size={28} className="text-emerald-400 mb-3" aria-hidden="true" />
                <p className="text-xs text-gray-500">{'\uD30C\uC77C \uC900\uBE44 \uC644\uB8CC. \uC544\uB798 \uBC84\uD2BC\uC744 \uB20C\uB7EC \uC5C5\uB85C\uB4DC\uB97C \uC2DC\uC791\uD558\uC138\uC694.'}</p>
              </div>
            )}

            <div className="space-y-3 overflow-y-auto" aria-live="polite">
              {feedback.errors.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-red-600 mb-1.5 flex items-center gap-1">
                    <AlertCircle size={11} aria-hidden="true" /> {'\uC624\uB958'} ({feedback.errors.length})
                  </p>
                  <ul className="space-y-1">
                    {feedback.errors.map((e, i) => (
                      <li key={i} className="text-[11px] text-red-600 bg-red-50 rounded p-2">{errToText(e)}</li>
                    ))}
                  </ul>
                </div>
              )}
              {feedback.warnings.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-orange-600 mb-1.5 flex items-center gap-1">
                    <AlertTriangle size={11} aria-hidden="true" /> {'\uACBD\uACE0'} ({feedback.warnings.length})
                  </p>
                  <ul className="space-y-1 max-h-32 overflow-y-auto">
                    {feedback.warnings.map((w, i) => (
                      <li key={i} className="text-[11px] text-orange-600 bg-orange-50 rounded p-2">{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {feedback.successes.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-blue-600 mb-1.5 flex items-center gap-1">
                    <Info size={11} aria-hidden="true" /> {'\uB9E4\uD551 \uC131\uACF5'} ({feedback.successes.length})
                  </p>
                  <ul className="space-y-1 max-h-32 overflow-y-auto">
                    {feedback.successes.slice(0, 6).map((s, i) => (
                      <li key={i} className="text-[11px] text-blue-600 bg-blue-50 rounded p-2">{s}</li>
                    ))}
                    {feedback.successes.length > 6 && (
                      <li className="text-[11px] text-blue-500 text-center">+{feedback.successes.length - 6}{'\uAC1C \uB354\uBCF4\uAE30'}</li>
                    )}
                  </ul>
                </div>
              )}
              {hasSubmitted && (createdCount > 0 || updatedCount > 0 || visitsAdded > 0) && (
                <div className="border-t border-gray-200 pt-3 mt-3">
                  <div className="rounded-xl bg-gradient-to-br from-emerald-50 to-emerald-100/50 border border-emerald-200 p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle size={20} className="text-emerald-500" aria-hidden="true" />
                      <p className="text-sm font-bold text-emerald-700">업로드 완료</p>
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-emerald-700/90 mb-3">
                      {createdCount > 0 && <span><b>신규 {createdCount}명</b></span>}
                      {updatedCount > 0 && <span><b>업데이트 {updatedCount}명</b></span>}
                      {visitsAdded > 0 && <span><b>검사 기록 {visitsAdded}건</b></span>}
                      {skippedCount > 0 && <span className="text-orange-600"><b>건너뜀 {skippedCount}건</b></span>}
                    </div>

                    {redirectIn !== null ? (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={goNow}
                          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-accent hover:bg-accent-dark text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                        >
                          <span aria-live="polite">{redirectLabel}로 이동 ({redirectIn}초)</span>
                          <ArrowRight size={12} aria-hidden="true" />
                        </button>
                        <button
                          onClick={cancelRedirect}
                          className="px-3 py-2 bg-white border border-gray-300 text-gray-600 text-xs font-semibold rounded-lg hover:bg-gray-50"
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={goNow}
                        className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-accent hover:bg-accent-dark text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                      >
                        {redirectLabel}로 이동
                        <ArrowRight size={12} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={submit}
            disabled={!file || uploading}
            className="w-full bg-accent text-white py-3.5 rounded-xl text-sm font-bold hover:bg-accent-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center justify-center gap-2"
          >
            {uploading ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                {'\uCC98\uB9AC \uC911...'}
              </>
            ) : (
              <>
                <Sparkles size={16} aria-hidden="true" />
                {'\uB370\uC774\uD130 \uCC98\uB9AC \uBC0F \uD504\uB85C\uD544 \uC0DD\uC131'}
              </>
            )}
          </button>
        </div>
      </div>
      )}
    </div>
  );
}
